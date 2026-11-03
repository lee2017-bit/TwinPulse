# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit stage routing: independent origins/credentials, no fallback/retry."""
from copy import deepcopy
from dataclasses import replace
import json

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


def _deref(node, root):
    """Follow root-local #/$defs/ (or #/definitions/) references only."""
    seen=set()
    while isinstance(node,dict) and isinstance(node.get('$ref'),str) and node['$ref'] not in seen:
        seen.add(node['$ref'])
        word,_,name=node['$ref'].removeprefix('#/').partition('/')
        target=root.get(word) if word in ('$defs','definitions') else None
        target=target.get(name) if isinstance(target,dict) else None
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


def _fits(value, node, root):
    """Structural match of the rows view of a host schema; only chooses anyOf/oneOf branches."""
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
        return set(node.get('required') or ())<=set(value) and all(
            _fits(item,properties[key],root) for key,item in value.items() if key in properties)
    if isinstance(value,list):
        schemas=[_item_schema(node,index) for index in range(len(value))]
        return all(schema is None or _fits(item,schema,root) for item,schema in zip(value,schemas))
    return True


def _restored(value, node, root):
    """(value, changed): rows back to the host map, walked with the host's own schema."""
    node=_deref(node,root)
    if not isinstance(node,dict):return value,False
    if _open_map(node):
        if not _rows(value):return value,False
        rows=[(row['name'],_restored(row['value'],node['additionalProperties'],root)[0]) for row in value]
        return (dict(rows) if len({name for name,_ in rows})==len(rows) else _RepeatedNames(rows)),True
    changed=False
    for word in ('anyOf','oneOf'):
        if isinstance(node.get(word),list):
            # Only an unambiguous branch converts; otherwise host validation sees the rows.
            options=[_restored(value,branch,root) for branch in node[word] if _fits(value,branch,root)]
            if any(moved for _,moved in options) and all(item==options[0][0] for item,_ in options):
                value,changed=options[0][0],True
    if isinstance(value,dict) and isinstance(node.get('properties'),dict):
        result={}
        for key,item in value.items():
            if key in node['properties']:
                item,moved=_restored(item,node['properties'][key],root);changed|=moved
            result[key]=item
        value=result
    elif isinstance(value,list):
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


def restore_open_maps(completion, schema):
    """Give the host its original map shape for an OpenAI rows completion.

    Unparseable, unmatched or duplicate-key content is returned unchanged:
    host validation stays the authority. Repeated row names become repeated
    JSON keys, which the host parser rejects as PROVIDER_JSON_DUPLICATE_KEY.
    """
    content=getattr(completion,'content',None)
    if not isinstance(content,str) or not open_map_paths(schema):return completion
    def unique(pairs):
        if len({key for key,_ in pairs})!=len(pairs):raise ValueError('repeated JSON key')
        return dict(pairs)
    try:
        value,changed=_restored(json.loads(content,object_pairs_hook=unique),schema,schema)
        text=_json_text(value) if changed else None
    except (ValueError,RecursionError):return completion
    return replace(completion,content=text) if changed else completion


def openai_observer_body(original, *, reasoning_effort='low'):
    """Equivalent stage contract; only OpenAI wire compatibility changes.

    Open maps travel as rows (restore_open_maps rebuilds them). A strict schema
    that OpenAI would still reject fails here, before any paid dispatch.
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
        envelope['schema']=compact_repeated_enum_schemas(openai_map_rows(envelope['schema']))
        problems=openai_strict_violations(envelope['schema']) if envelope.get('strict') is True else []
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
            return restore_open_maps(await self.observer.complete(openai_observer_body(body,
                reasoning_effort=self.reasoning_effort), token, self.observer_config),
                body['response_format']['json_schema'].get('schema'))
        if (schema in {'twinpulse_site_tool_plan_v2', 'twinpulse_compact_photo_layout'}
                and body.get('model') == self.planner_config.model_id and not has_image(body['messages'])):
            if not self.openai_planner:
                return await self.planner.complete(body, token, self.planner_config)
            wire = openai_observer_body(body, reasoning_effort=self.reasoning_effort)
            return restore_open_maps(await self.planner.complete(wire, token, self.planner_config),
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
        # OpenAI receives open maps as rows; the host validates its original shape.
        schema = wire['response_format']['json_schema']['schema']
        result = await self.transports[stage].complete(openai_observer_body(wire,
            reasoning_effort=self.reasoning[stage]), token, config)
        return restore_open_maps(result, schema)
