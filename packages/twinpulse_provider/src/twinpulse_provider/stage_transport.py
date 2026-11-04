# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit stage routing: independent origins/credentials, no fallback/retry."""
from copy import deepcopy
from dataclasses import replace
import json
from urllib.parse import unquote

from .errors import ProviderConfigurationError

OPENAI_MINI_SNAPSHOT = 'gpt-5.4-mini-2026-03-17'
WIRE_CONTRACT_REVISION = 'explicit-json-contract-1.4'
# OpenAI strict Structured Outputs: keywords it rejects, and the row bound of a
# string-keyed map sent as [{name, value}] rows when the map sets no maxProperties.
OPENAI_UNSUPPORTED_KEYWORDS = ('allOf', 'not', 'if', 'then', 'else', 'dependentRequired', 'dependentSchemas',
                               'patternProperties')
OPEN_MAP_MAX_ROWS = 32
_OPEN_MAP_WORDS = {'type', 'additionalProperties', 'properties', 'required', 'maxProperties', 'minProperties',
                   'description', 'title'}
# Wire-only wrappers: a root that is not a plain object travels as {"value": root},
# and an optional property that itself accepts null travels as {"set": value}.
_ROOT_KEY = 'value'
_BOX_KEY = 'set'


def _map_schema_children(node, visit):
    """Visit schemas, never property/definition maps or instance annotations.

    A ``properties`` value is a map *of* schemas, not itself a schema. A $ref
    in that map means a property literally named '$ref', not indirection.
    """
    result=deepcopy(node)
    for name in ('properties','patternProperties','dependentSchemas'):
        if isinstance(node.get(name),dict):
            result[name]={key:visit(value) for key,value in node[name].items()}
    for name in ('items','additionalProperties','additionalItems','contains',
                 'propertyNames','not','if','then','else','unevaluatedProperties','unevaluatedItems'):
        value=node.get(name)
        if isinstance(value,dict):result[name]=visit(value)
        elif name=='items' and isinstance(value,list):result[name]=[visit(v) for v in value]
    for name in ('anyOf','allOf','oneOf','prefixItems'):
        if isinstance(node.get(name),list):result[name]=[visit(v) for v in node[name]]
    return result


def compact_schema_subtrees(original):
    """Exact local references, including repeated placement object branches."""
    import hashlib
    import json
    schema = deepcopy(original)
    counts = {}
    def key(node):
        return json.dumps(node, sort_keys=True, separators=(',', ':'))
    def count(node):
        if not isinstance(node,dict):return node
        spelling = key(node)
        if len(spelling) >= 160 and not {'$ref','$defs','definitions','$id'} & set(node):
            counts[spelling] = counts.get(spelling, 0) + 1
        _map_schema_children(node,count)
        return node
    count(schema)
    definitions = deepcopy(schema.get('$defs', {}))
    def compact(node, root=False):
        if not isinstance(node, dict): return node
        spelling = key(node)
        result = _map_schema_children(node,compact)
        if not root and counts.get(spelling, 0) > 1:
            name = 'shared_' + hashlib.sha256(spelling.encode()).hexdigest()[:16]
            while name in definitions and definitions[name] != result: name += 'x'
            definitions[name] = result
            return {'$ref': '#/$defs/' + name}
        return result
    result = compact(schema, root=True)
    if definitions: result['$defs'] = definitions
    return result


def normalize_json_schema(schema):
    """Equivalent schema spelling shared by the two configured providers."""
    schema = deepcopy(schema)
    def normalize(node):
        if isinstance(node, dict):
            node=_map_schema_children(node,normalize)
            for name in ('$defs','definitions'):
                if isinstance(node.get(name),dict):
                    node[name]={key:normalize(child) for key,child in node[name].items()}
            if 'const' in node:
                node['enum'] = [node.pop('const')]
            if 'enum' in node and 'type' not in node:
                types = []
                for value in node['enum']:
                    kind = ('null' if value is None else 'boolean' if type(value) is bool else
                        'integer' if type(value) is int else 'number' if type(value) is float else
                        'string' if isinstance(value, str) else None)
                    if kind is None:
                        raise ProviderConfigurationError('Unsupported enum type in response schema')
                    if kind not in types: types.append(kind)
                if not types:
                    raise ProviderConfigurationError('Empty enum in response schema')
                node['type'] = types[0] if len(types) == 1 else types
        return node
    return normalize(schema)


def explicit_json_contract(original):
    body = deepcopy(original)
    envelope = body.get('response_format', {}).get('json_schema')
    if not envelope:
        raise ProviderConfigurationError('A host-owned JSON schema is required')
    envelope['schema'] = normalize_json_schema(envelope['schema'])
    # Keep the proven provider grammar spelling; only the redundant prompt
    # copy uses exact references. A provider need not compile new $defs shapes.
    prompt_schema=compact_schema_subtrees(envelope['schema'])
    note = '\nResponse JSON Schema:\n'+__import__('json').dumps(prompt_schema, separators=(',', ':'))
    systems = [row for row in body['messages'] if row.get('role') == 'system']
    if len(systems) != 1 or not isinstance(systems[0].get('content'), str):
        raise ProviderConfigurationError('One text system instruction is required')
    # Repeated routing must replace the old exact contract, not append copies.
    systems[0]['content'] = systems[0]['content'].split('\nResponse JSON Schema:\n', 1)[0] + note
    return body


def compact_repeated_enum_schemas(original):
    """Factor identical enum leaves without widening any accepted value.

    Structured Outputs limits the total number of enum values per schema.
    Repeating the same library/placement enum for each object used to exceed
    that limit even for a modest scene. Root-local $defs/$ref are supported;
    host validation still uses the original semantic schema independently.
    """
    import hashlib
    import json
    schema=deepcopy(original)
    counts={};leaves={}
    def visit(node):
        if isinstance(node,dict):
            if 'enum' in node and len(node['enum'])>1 and '$ref' not in node:
                key=json.dumps(node,sort_keys=True,separators=(',',':'))
                counts[key]=counts.get(key,0)+1;leaves[key]=node
            for child in node.values():visit(child)
        elif isinstance(node,list):
            for child in node:visit(child)
    visit(schema)
    definitions=deepcopy(schema.get('$defs',{}));references={}
    for key,count in counts.items():
        if count<2:continue
        name='shared_enum_'+hashlib.sha256(key.encode()).hexdigest()[:16]
        while name in definitions and definitions[name]!=leaves[key]:name+='x'
        definitions[name]=deepcopy(leaves[key]);references[key]='#/$defs/'+name
    def replace(node):
        if isinstance(node,dict):
            key=json.dumps(node,sort_keys=True,separators=(',',':')) if 'enum' in node else None
            if key in references:return {'$ref':references[key]}
            return {key:replace(child) for key,child in node.items() if key!='$defs'}
        if isinstance(node,list):return [replace(child) for child in node]
        return node
    result=replace(schema)
    if definitions:result['$defs']=definitions
    def enum_count(node):
        if isinstance(node,dict):return len(node.get('enum',[]))+sum(enum_count(c) for c in node.values())
        if isinstance(node,list):return sum(enum_count(c) for c in node)
        return 0
    count=enum_count(result)
    if count>1000:
        # Different ID lists (e.g. all duplicate targets except oneself) overlap
        # heavily but are not identical. Share their exact singleton members,
        # rather than allowing a broader global ID enum and relaxing validation.
        members=deepcopy(result.get('$defs',{}))
        def singletons(node):
            if isinstance(node,dict):
                if 'enum' in node and len(node['enum'])>1:
                    references=[]
                    for value in node['enum']:
                        leaf={**deepcopy(node),'enum':[value]}
                        key=json.dumps(leaf,sort_keys=True,separators=(',',':'))
                        name='enum_member_'+hashlib.sha256(key.encode()).hexdigest()[:16]
                        while name in members and members[name]!=leaf:name+='x'
                        members[name]=leaf;references.append({'$ref':'#/$defs/'+name})
                    return {'anyOf':references}
                return {key:singletons(child) for key,child in node.items() if key!='$defs'}
            if isinstance(node,list):return [singletons(child) for child in node]
            return node
        reduced=singletons(result)
        # Existing definitions can contain remaining overlapping leaf enums.
        # Traverse a frozen copy; newly registered singleton definitions need
        # no further expansion and cannot form recursive references.
        for name,value in list(result.get('$defs',{}).items()):members[name]=singletons(value)
        reduced['$defs']=members;result=reduced;count=enum_count(result)
    if count>1000:
        raise ProviderConfigurationError(f'Structured output schema still contains {count} enum values after exact deduplication; limit is 1000. No dispatch.')
    return result


def _subschemas(node, path):
    """(word, key, path, child) per direct subschema; property maps are not schemas."""
    for word in ('properties','patternProperties','dependentSchemas','$defs','definitions'):
        if isinstance(node.get(word),dict):
            for key,child in node[word].items():
                yield word,key,(path+'.'+key if word=='properties' else f'{path}.{word}.{key}'),child
    for word in ('items','additionalProperties','additionalItems','contains','propertyNames',
                 'not','if','then','else','unevaluatedProperties','unevaluatedItems'):
        if isinstance(node.get(word),dict):yield word,None,path+'.'+word,node[word]
    for word in ('anyOf','allOf','oneOf','prefixItems','items'):
        if isinstance(node.get(word),list):
            for key,child in enumerate(node[word]):yield word,key,f'{path}.{word}[{key}]',child


def _ref_target(ref, root):
    """What a local reference names when it is the root ('#') or a whole root definition, else None.

    The OpenAI wire spells exactly these targets as wholes (a wrapped root moves
    its definitions up beside it and '#' becomes '#/properties/value'), so only
    these keep their meaning on the wire and in restore_openai_wire.
    """
    if not (isinstance(ref,str) and ref.startswith('#') and isinstance(root,dict)):return None
    pointer=unquote(ref[1:])  # a URI fragment that holds an RFC 6901 JSON pointer
    if not pointer:return root
    tokens=[token.replace('~1','/').replace('~0','~') for token in pointer.split('/')]
    if len(tokens)!=3 or tokens[0] or tokens[1] not in ('$defs','definitions'):return None
    table=root.get(tokens[1])
    return table.get(tokens[2]) if isinstance(table,dict) else None


def _deref(node, root):
    """Follow references to the root or a whole root definition (_ref_target); any other stays as written."""
    seen=set()
    while isinstance(node,dict) and isinstance(node.get('$ref'),str) and node['$ref'] not in seen:
        seen.add(node['$ref'])
        target=_ref_target(node['$ref'],root)
        if not isinstance(target,dict):break
        node=target
    return node


def _object_schema(node):
    kind=node.get('type')
    return kind=='object' or (isinstance(kind,list) and 'object' in kind) or 'properties' in node


def openai_strict_violations(schema):
    """(json_path, rule) pairs that OpenAI strict Structured Outputs rejects.

    Closed objects, every property required, no unsupported keyword, an object
    root. Depth is only reported (openai_schema_depth): how OpenAI counts it is
    unverified, so depth alone never blocks a request.
    """
    found=[]
    if not isinstance(schema,dict) or schema.get('type')!='object' or 'anyOf' in schema:
        found.append(('$','root_not_object'))
    def visit(node, path):
        if not isinstance(node,dict):return
        found.extend((path,'unsupported_'+word) for word in OPENAI_UNSUPPORTED_KEYWORDS if word in node)
        if _object_schema(node):
            if node.get('additionalProperties') is not False:found.append((path,'additional_properties_not_false'))
            if set(node.get('required') or ())!=set(node.get('properties') or ()):
                found.append((path,'required_not_all_properties'))
        for _,_,child_path,child in _subschemas(node,path):visit(child,child_path)
    visit(schema,'$')
    return found


def openai_schema_depth(schema):
    """Deepest object below the root object (root = 0), through $ref; a cycle counts once."""
    def depth(node, refs):
        if not isinstance(node,dict):return -1
        if isinstance(node.get('$ref'),str):
            target=_deref(node,schema)
            return -1 if target is node or node['$ref'] in refs else depth(target,refs|{node['$ref']})
        below=max((depth(child,refs) for word,_,_,child in _subschemas(node,'$')
                   if word not in ('$defs','definitions')),default=-1)
        return below+1 if _object_schema(node) else below
    return depth(schema,frozenset())


def _open_map(node):
    """A string-keyed map: one value schema, no fixed keys, nothing the rows would lose."""
    return (isinstance(node,dict) and node.get('type')=='object' and isinstance(node.get('additionalProperties'),dict)
            and not node.get('properties') and not node.get('required') and set(node)<=_OPEN_MAP_WORDS)


def open_map_paths(schema):
    """JSON paths of the maps that the OpenAI wire sends as rows."""
    if not isinstance(schema,dict):return []
    found=[]
    def visit(node, path):
        if _open_map(node):found.append(path)
        for _,_,child_path,child in _subschemas(node,path):
            if isinstance(child,dict):visit(child,child_path)
    visit(schema,'$')
    return found


def openai_map_rows(schema):
    """Lossless OpenAI strict spelling: each open map becomes bounded [{name, value}] rows.

    The value schema is unchanged. Any other open object stays as written, so
    openai_strict_violations still rejects it locally.
    """
    def visit(node):
        if not isinstance(node,dict):return node
        for word,key,_,child in list(_subschemas(node,'$')):
            if key is None:node[word]=visit(child)
            else:node[word][key]=visit(child)
        if not _open_map(node):return node
        rows={'type':'array','items':{'type':'object','additionalProperties':False,'required':['name','value'],
            'properties':{'name':{'type':'string','maxLength':64},'value':node['additionalProperties']}},
            'maxItems':node.get('maxProperties',OPEN_MAP_MAX_ROWS)}
        if 'minProperties' in node:rows['minItems']=node['minProperties']
        rows.update({word:node[word] for word in ('description','title') if word in node})
        return rows
    return visit(deepcopy(schema))


def _accepts_null(node, root, refs=frozenset()):
    """False only when this schema certainly rejects null; anything unclear counts as accepting it."""
    if isinstance(node,dict) and isinstance(node.get('$ref'),str):
        target=_deref(node,root)
        if target is node or node['$ref'] in refs:return True
        return _accepts_null(target,root,refs|{node['$ref']})
    if not isinstance(node,dict):return node is not False
    kinds=node.get('type')
    if (('const' in node and node['const'] is not None) or (isinstance(node.get('enum'),list) and None not in node['enum'])
            or (isinstance(kinds,str) and kinds!='null') or (isinstance(kinds,list) and 'null' not in kinds)):
        return False
    if any(isinstance(node.get(word),list) and not any(_accepts_null(branch,root,refs) for branch in node[word])
           for word in ('anyOf','oneOf')):return False
    return not (isinstance(node.get('allOf'),list) and not all(_accepts_null(part,root,refs) for part in node['allOf']))


def _closed_object(node):
    """A closed object whose every property the wire sends: one without anyOf/oneOf beside its properties."""
    return (isinstance(node,dict) and node.get('additionalProperties') is False
            and isinstance(node.get('properties'),dict) and 'anyOf' not in node and 'oneOf' not in node)


def _optional_properties(node, root):
    """{name: boxed} for each optional property of a closed object, in property order.

    The OpenAI wire requires all of them; null there means "left out", so a
    property that itself accepts null is boxed as {"set": value}. A node that
    also carries anyOf/oneOf is not rewritten: the strict check rejects it.
    Rows keep every closed object and the null acceptance of every schema, so
    this gives the same answer for the host schema and its map-rows spelling.
    """
    if not _closed_object(node):return {}
    required=node.get('required') or ()
    return {key:_accepts_null(child,root) for key,child in node['properties'].items() if key not in required}


def _optional_fields(schema):
    """Every optional property of a closed object becomes required: nullable, or boxed (see _optional_properties)."""
    def visit(node):
        if not isinstance(node,dict):return node
        optional=_optional_properties(node,schema)  # decided on the unchanged input
        for word,key,_,child in list(_subschemas(node,'$')):
            if key is None:node[word]=visit(child)
            else:node[word][key]=visit(child)
        for key,boxed in optional.items():
            field=node['properties'][key]
            if boxed:
                field={'type':'object','additionalProperties':False,'required':[_BOX_KEY],'properties':{_BOX_KEY:field},
                       'description':'Wraps a value that may itself be null; plain null leaves the field out.'}
            node['properties'][key]={'anyOf':[{'type':'null'},field]}
        if optional:node['required']=[*(node.get('required') or ()),*optional]
        return node
    return visit(deepcopy(schema))


def _rewrites(node, root, refs=frozenset()):
    """Whether the wire spells this host subschema differently: an open map or an optional property below it."""
    if isinstance(node,dict) and isinstance(node.get('$ref'),str):
        target=_deref(node,root)
        return target is not node and node['$ref'] not in refs and _rewrites(target,root,refs|{node['$ref']})
    if not isinstance(node,dict):return False
    return bool(_open_map(node) or _optional_properties(node,root)) or any(_rewrites(child,root,refs)
        for word,_,_,child in _subschemas(node,'$') if word not in ('$defs','definitions'))


def _wraps_root(schema):
    """Whether the OpenAI wire root is {"value": host root}: strict mode needs a plain object root."""
    return isinstance(schema,dict) and (schema.get('type')!='object' or 'anyOf' in schema or 'oneOf' in schema
                                        or _open_map(schema))


def _object_root(schema):
    """{"value": schema}. Root definitions move up beside it and a reference to the root, '#',
    becomes '#/properties/value', so every reference _ref_target follows names the same subschema."""
    def rebase(node):
        if not isinstance(node,dict):return node
        for word,key,_,child in list(_subschemas(node,'$')):
            if key is None:node[word]=rebase(child)
            else:node[word][key]=rebase(child)
        if node.get('$ref')=='#':node['$ref']='#/properties/'+_ROOT_KEY
        return node
    inner=rebase(deepcopy(schema))
    root={'type':'object','additionalProperties':False,'required':[_ROOT_KEY],'properties':{_ROOT_KEY:inner}}
    for word in ('$defs','definitions'):
        if word in inner:root[word]=inner.pop(word)
    return root


def openai_wire_schema(schema):
    """The OpenAI strict spelling of a host schema, decided by the host schema alone.

    In order: open maps become rows (openai_map_rows); every optional property
    of a closed object becomes required, null meaning "left out" and a
    property that itself accepts null boxed as {"set": value}; a root that is
    not a plain object becomes {"value": root}. restore_openai_wire is the
    exact inverse for every strict schema openai_observer_body sends: one whose
    references name the root or a root definition and whose anyOf/oneOf
    branches, where the wire rewrites one, share no wire value (_wire_issues).
    Anything else stays as written, so openai_strict_violations still rejects
    it locally.
    """
    wire=_optional_fields(openai_map_rows(schema))
    return _object_root(wire) if _wraps_root(schema) else wire


class _RepeatedNames(list):
    """Rows whose names repeat; written back as repeated JSON keys, never merged."""


def _rows(value):
    return isinstance(value,list) and all(isinstance(row,dict) and set(row)=={'name','value'}
        and isinstance(row['name'],str) for row in value)


def _same(value, expected):
    return value==expected and isinstance(value,bool)==isinstance(expected,bool)


def _item_schema(node, index):
    prefix=node.get('prefixItems',node.get('items'))
    if isinstance(prefix,list):
        return prefix[index] if index<len(prefix) else node.get('items') if isinstance(node.get('items'),dict) else None
    return prefix if isinstance(prefix,dict) else None


def _boxed(value):
    return isinstance(value,dict) and set(value)=={_BOX_KEY}


def _fits(value, node, root):
    """Structural match of the OpenAI wire view of a host schema; only chooses anyOf/oneOf branches."""
    node=_deref(node,root)
    if not isinstance(node,dict):return node is not False
    if 'const' in node and not _same(value,node['const']):return False
    if 'enum' in node and not any(_same(value,item) for item in node['enum']):return False
    if any(isinstance(node.get(word),list) and not any(_fits(value,branch,root) for branch in node[word])
           for word in ('anyOf','oneOf')):return False
    if _open_map(node):
        return _rows(value) and all(_fits(row['value'],node['additionalProperties'],root) for row in value)
    kinds=node.get('type');kinds=kinds if isinstance(kinds,list) else [kinds] if kinds else []
    matches={'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
        'null':value is None,'boolean':isinstance(value,bool),
        'integer':isinstance(value,int) and not isinstance(value,bool),
        'number':isinstance(value,(int,float)) and not isinstance(value,bool)}
    if kinds and not any(matches.get(kind,True) for kind in kinds):return False
    if isinstance(value,dict):
        properties=node.get('properties') if isinstance(node.get('properties'),dict) else {}
        if node.get('additionalProperties') is False and not set(value)<=set(properties):return False
        optional=_optional_properties(node,root)  # all of them are required on the wire
        return (set(node.get('required') or ())|set(optional))<=set(value) and all(
            _fits_field(item,properties[key],optional.get(key),root) for key,item in value.items() if key in properties)
    if isinstance(value,list):
        schemas=[_item_schema(node,index) for index in range(len(value))]
        return all(schema is None or _fits(item,schema,root) for item,schema in zip(value,schemas))
    return True


def _fits_field(value, node, boxed, root):
    """One property in its wire view; boxed is None when the host requires the property too."""
    if boxed is None:return _fits(value,node,root)
    if value is None:return True  # left out
    if boxed:return _boxed(value) and _fits(value[_BOX_KEY],node,root)
    return _fits(value,node,root)


_JSON_TYPES = {'object', 'array', 'string', 'null', 'boolean', 'integer', 'number'}


def _wire_types(node):
    """JSON types a value fitting this host node can have on the wire (rows are arrays); None if unknown."""
    if _open_map(node):return {'array'}
    kinds=node.get('type');kinds=kinds if isinstance(kinds,list) else [kinds] if kinds else []  # as _fits reads it
    if not kinds or not set(kinds)<=_JSON_TYPES:return None
    return set(kinds)|({'integer'} if 'number' in kinds else set())  # an integer fits number too


def _disjoint(one, other, root, depth=0):
    """True only when no wire value can fit both host schemas (see _fits); False when unsure."""
    one,other=_deref(one,root),_deref(other,root)
    if depth>32 or not (isinstance(one,dict) and isinstance(other,dict)):return False
    kinds=_wire_types(one),_wire_types(other)
    if None not in kinds and not kinds[0]&kinds[1]:return True
    values=[[node['const']] if 'const' in node else node.get('enum') if isinstance(node.get('enum'),list) else None
            for node in (one,other)]
    if None not in values and not any(_same(a,b) for a in values[0] for b in values[1]):return True
    if kinds!=({'object'},{'object'}):return False
    # A closed object's wire value carries exactly its property names.
    if _closed_object(one) and _closed_object(other) and set(one['properties'])!=set(other['properties']):return True
    # A property that both require is sent as written (never null for "left out").
    first,second=(node['properties'] if isinstance(node.get('properties'),dict) else {} for node in (one,other))
    shared=[key for key in one.get('required') or () if key in (other.get('required') or ())]
    return any(key in first and key in second and _disjoint(first[key],second[key],root,depth+1) for key in shared)


def _restored(value, node, root):
    """(value, changed): the host value of a wire value, walked with the host's own schema.

    Rows become the map, a null optional property is left out and a box is opened.
    """
    node=_deref(node,root)
    if not isinstance(node,dict):return value,False
    if _open_map(node):
        if not _rows(value):return value,False
        rows=[(row['name'],_restored(row['value'],node['additionalProperties'],root)[0]) for row in value]
        return (dict(rows) if len({name for name,_ in rows})==len(rows) else _RepeatedNames(rows)),True
    changed=False
    for word in ('anyOf','oneOf'):
        if isinstance(node.get(word),list):
            # Only an unambiguous branch converts; otherwise host validation sees the wire spelling.
            options=[_restored(value,branch,root) for branch in node[word] if _fits(value,branch,root)]
            if any(moved for _,moved in options) and all(item==options[0][0] for item,_ in options):
                value,changed=options[0][0],True
    if isinstance(value,dict) and isinstance(node.get('properties'),dict):
        optional=_optional_properties(node,root)
        result={}
        for key,item in value.items():
            boxed=optional.get(key)
            if boxed is not None and item is None:
                changed=True;continue  # the host leaves this property out
            if boxed and not _boxed(item):
                result[key]=item;continue  # not a box: left as sent for host validation
            if boxed:item,changed=item[_BOX_KEY],True
            if key in node['properties']:
                item,moved=_restored(item,node['properties'][key],root);changed|=moved
            result[key]=item
        value=result
    elif isinstance(value,list) and not isinstance(value,_RepeatedNames):  # an anyOf map stays one object
        result=[]
        for index,item in enumerate(value):
            schema=_item_schema(node,index)
            if schema is not None:
                item,moved=_restored(item,schema,root);changed|=moved
            result.append(item)
        value=result
    return value,changed


def _json_text(value):
    if isinstance(value,(dict,_RepeatedNames)):
        return '{'+','.join(_json_text(key)+':'+_json_text(item)
                            for key,item in (value.items() if isinstance(value,dict) else value))+'}'
    if isinstance(value,list):return '['+','.join(_json_text(item) for item in value)+']'
    text=json.dumps(value,ensure_ascii=False)
    try:text.encode('utf-8')
    except UnicodeEncodeError:return json.dumps(value)  # a lone surrogate stays escaped
    return text


def restore_openai_wire(completion, schema):
    """Give the host its own JSON shape back for a completion of openai_wire_schema(schema).

    The exact inverse for every strict schema openai_observer_body sends, walked
    with the host schema: a wrapped root is unwrapped, rows become maps, a null
    optional property is left out and a {"set": v} box becomes v. A part that
    is unmatched keeps its wire spelling (an ambiguous one cannot reach here:
    _wire_issues refuses such a schema before dispatch); unparseable or
    duplicate-key content, or a wrapped root that is not exactly
    {"value": ...}, is returned unchanged. Host validation stays the
    authority. Repeated row names become repeated JSON keys, which the host
    parser rejects as PROVIDER_JSON_DUPLICATE_KEY. Only for OpenAI wire
    completions: a host-shaped (Nebius) reply is not a wire spelling.
    """
    content=getattr(completion,'content',None)
    if not isinstance(content,str) or not isinstance(schema,dict) or openai_wire_schema(schema)==schema:
        return completion
    def unique(pairs):
        if len({key for key,_ in pairs})!=len(pairs):raise ValueError('repeated JSON key')
        return dict(pairs)
    try:
        value=json.loads(content,object_pairs_hook=unique)
        wrapped=_wraps_root(schema)
        if wrapped:
            if not (isinstance(value,dict) and set(value)=={_ROOT_KEY}):return completion
            value=value[_ROOT_KEY]
        value,changed=_restored(value,schema,schema)
        text=_json_text(value) if changed or wrapped else None
    except (ValueError,RecursionError):return completion
    return completion if text is None else replace(completion,content=text)


def _wire_issues(schema):
    """(json_path, rule) for host shapes whose OpenAI wire spelling restore_openai_wire could not invert exactly.

    ref_not_root_or_definition: the wire may move or widen any other target,
    and the restore does not follow it. anyOf/oneOf_branches_not_disjoint: one
    wire value might fit two branches, one of them rewritten, that restore to
    different host values; the host could then read it as the other branch.
    """
    found=[]
    def visit(node, path):
        if not isinstance(node,dict):return
        if isinstance(node.get('$ref'),str) and not isinstance(_ref_target(node['$ref'],schema),dict):
            found.append((path,'ref_not_root_or_definition'))
        for word in ('anyOf','oneOf'):
            branches=node.get(word)
            if not isinstance(branches,list):continue
            rewritten=[_rewrites(branch,schema) for branch in branches]
            if not all(_disjoint(one,other,schema) for i,one in enumerate(branches)
                       for j,other in enumerate(branches) if i<j and (rewritten[i] or rewritten[j])):
                found.append((path,word+'_branches_not_disjoint'))
        for _,_,child_path,child in _subschemas(node,path):visit(child,child_path)
    visit(schema,'$')
    return found


def openai_observer_body(original, *, reasoning_effort='low'):
    """Equivalent stage contract; only OpenAI wire compatibility changes.

    The schema travels in its OpenAI strict spelling (openai_wire_schema);
    restore_openai_wire gives a completion back its host shape. A strict
    schema that OpenAI would still reject, or whose wire spelling could not be
    restored exactly (_wire_issues), fails here, before any paid dispatch.
    """
    body = deepcopy(original)
    if 'chat_template_kwargs' in body:
        raise ProviderConfigurationError('Nebius template flags cannot be sent to OpenAI')
    body['max_completion_tokens'] = body.pop('max_tokens')
    body.pop('temperature', None)
    body['reasoning_effort'] = reasoning_effort
    body['response_format'] = normalize_json_schema(body['response_format'])
    envelope=body['response_format'].get('json_schema')
    if envelope:
        host=envelope['schema']
        envelope['schema']=compact_repeated_enum_schemas(openai_wire_schema(host))
        problems=(_wire_issues(host)+openai_strict_violations(envelope['schema'])
                  if envelope.get('strict') is True else [])
        if problems:
            error=ProviderConfigurationError('OpenAI strict schema invalid before dispatch: '+', '.join(
                path+' '+rule for path,rule in problems[:3])+(f' (+{len(problems)-3} more)' if len(problems)>3 else ''))
            error.code='OPENAI_STRICT_SCHEMA_INVALID'
            raise error
    return body


def has_image(value):
    if isinstance(value, dict):
        return value.get('type') in ('image_url', 'input_image') or any(has_image(v) for v in value.values())
    if isinstance(value, list):
        return any(has_image(v) for v in value)
    return isinstance(value, str) and 'data:image/' in value


class StageRoutingTransport:
    def __init__(self, observer, observer_config, planner, planner_config, *, reasoning_effort='low',
                 openai_planner=False):
        planner_origin = 'https://api.openai.com/v1/' if openai_planner else 'https://api.tokenfactory.nebius.com/v1/'
        planner_model = OPENAI_MINI_SNAPSHOT if openai_planner else 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
        if (observer_config.base_url != 'https://api.openai.com/v1/'
                or planner_config.base_url != planner_origin
                or observer_config.endpoint_path != 'chat/completions'
                or planner_config.endpoint_path != 'chat/completions'
                or observer_config.model_id != OPENAI_MINI_SNAPSHOT
                or planner_config.model_id != planner_model
                or reasoning_effort not in {'low', 'medium', 'high'}):
            raise ProviderConfigurationError('Reviewed split provider origins/models required')
        self.observer, self.observer_config = observer, observer_config
        self.planner, self.planner_config = planner, planner_config
        self.reasoning_effort = reasoning_effort
        self.openai_planner = openai_planner

    async def complete(self, body, token, _pipeline_config):
        schema = body.get('response_format', {}).get('json_schema', {}).get('name')
        if schema == 'twinpulse_image_observation' and body.get('model') == self.observer_config.model_id:
            return restore_openai_wire(await self.observer.complete(openai_observer_body(body,
                reasoning_effort=self.reasoning_effort), token, self.observer_config),
                body['response_format']['json_schema'].get('schema'))
        if (schema in {'twinpulse_site_tool_plan_v2', 'twinpulse_compact_photo_layout'}
                and body.get('model') == self.planner_config.model_id and not has_image(body['messages'])):
            if not self.openai_planner:
                return await self.planner.complete(body, token, self.planner_config)
            wire = openai_observer_body(body, reasoning_effort=self.reasoning_effort)
            return restore_openai_wire(await self.planner.complete(wire, token, self.planner_config),
                body['response_format']['json_schema'].get('schema'))
        raise ProviderConfigurationError('Unknown stage/model or image leakage to planner; no dispatch')


class ConfiguredStageTransport:
    """Reviewed ordinary settings, independent of host-only evaluation scopes."""
    def __init__(self, transports, configs, providers, reasoning, *, model_catalog=None, harness_bindings=None):
        allowed = {
            'observer': {'openai': {OPENAI_MINI_SNAPSHOT,'gpt-6-luna'},
                         'nebius': {'google/gemma-3-27b-it', 'openbmb/MiniCPM-V-4_5', 'deepseek-ai/DeepSeek-V4.1-Flash', 'Qwen/Qwen3.8-27B'}},
            'planner': {'openai': {OPENAI_MINI_SNAPSHOT,'gpt-6-luna'},
                        'nebius': {'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B', 'nvidia/Nemotron-3_5-Lightning'}},
        }
        origins = {'openai': 'https://api.openai.com/v1/', 'nebius': 'https://api.tokenfactory.nebius.com/v1/'}
        if model_catalog is not None:
            from .model_contracts import checked_catalog,model_supported
            model_catalog=checked_catalog(model_catalog)
            for stage in allowed:
                allowed[stage]['nebius']={r['model_id'] for r in model_catalog['models']
                    if model_supported(model_catalog,stage,r['model_id'])}
        for mapping in (transports, configs, providers, reasoning):
            if set(mapping) != {'observer', 'planner'}:
                raise ProviderConfigurationError('Both configured stages are required')
        for stage, config in configs.items():
            provider = providers[stage]
            if (provider not in origins or config.base_url != origins[provider]
                    or config.endpoint_path != 'chat/completions'
                    or config.model_id not in allowed[stage][provider]
                    or reasoning[stage] not in ({'none'} if config.model_id=='gpt-6-luna' else {'low', 'medium', 'high'})):
                raise ProviderConfigurationError('Unsupported configured stage origin/model')
        self.transports, self.configs = dict(transports), dict(configs)
        self.providers, self.reasoning = dict(providers), dict(reasoning)
        from .harness_profiles import checked_binding
        self.harness_bindings = deepcopy(harness_bindings) or None
        for stage, frozen in (self.harness_bindings or {}).items():
            if stage not in ('observer', 'planner'):
                raise ProviderConfigurationError('Unknown harness stage')
            try:
                checked_binding(frozen, provider=providers[stage], model=configs[stage].model_id, role=stage)
            except (KeyError, TypeError, ValueError):
                raise ProviderConfigurationError('Configured harness identity mismatch') from None

    def record_validation(self, stage, attempt_id, record):
        owner = 'observer' if stage in ('observer', 'observer_structure', 'render_review') else 'planner'
        recorder = getattr(self.transports[owner], 'record_validation', None)
        if recorder:
            recorder(stage, attempt_id, record)

    async def complete(self, body, token, _pipeline_config):
        schema = body.get('response_format', {}).get('json_schema', {}).get('name')
        if schema in ('twinpulse_image_observation', 'twinpulse_room_observation', 'twinpulse_render_review','twinpulse_asset_observation','twinpulse_environment_photo'):
            stage = 'observer'
        elif schema in {'twinpulse_site_tool_plan_v2', 'twinpulse_compact_photo_layout',
                        'twinpulse_semantic_room', 'twinpulse_semantic_structure', 'twinpulse_model_resolution', 'twinpulse_model_recipe', 'twinpulse_semantic_batch', 'twinpulse_semantic_patch',
                        'twinpulse_scene_feedback','twinpulse_library_recipe','twinpulse_environment_move','twinpulse_robot_task'}:
            stage = 'planner'
            if has_image(body.get('messages')):
                raise ProviderConfigurationError('Images cannot be dispatched to the planner')
        else:
            raise ProviderConfigurationError('Unknown configured stage; no dispatch')
        config = self.configs[stage]
        budget = getattr(token, 'generation_budget', None)
        if budget is not None:
            config = replace(config, timeout_s=min(config.timeout_s,
                budget.timeout_for(getattr(token, 'generation_role', 'initial'))))
        if body.get('model') != config.model_id:
            raise ProviderConfigurationError('Configured stage model mismatch; no dispatch')
        if self.harness_bindings and stage in self.harness_bindings:
            from .harness_profiles import apply_profile
            # Host stage is independent of initial/repair/final budget roles.
            host_stage = getattr(token, 'harness_stage', None)
            hint = ('structure' if stage == 'observer' and host_stage == 'observer_structure' else None)
            try:
                body = apply_profile(body, self.harness_bindings[stage], stage_hint=hint,
                    repairing=stage == 'planner' and getattr(token, 'generation_role', None) == 'repair')
            except (KeyError, TypeError, ValueError):
                raise ProviderConfigurationError('Configured harness composition failed') from None
        wire = explicit_json_contract(body)
        if self.providers[stage] != 'openai':
            return await self.transports[stage].complete(wire, token, config)
        # OpenAI receives the strict spelling of the schema; the host validates its original shape.
        schema = wire['response_format']['json_schema']['schema']
        result = await self.transports[stage].complete(openai_observer_body(wire,
            reasoning_effort=self.reasoning[stage]), token, config)
        return restore_openai_wire(result, schema)
