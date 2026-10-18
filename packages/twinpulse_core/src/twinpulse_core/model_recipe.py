# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Version-pinned local furniture recipes. Data only, never executable code.

v1 is an assembly of local axis-aligned boxes, rotated as a whole instance.
Supports are actual box tops, not model-authored floating planes. Every use
revalidates its parameters; boundary samples do not prove a whole domain.
"""
from copy import deepcopy
from itertools import product
import json
import math
import re

from .models import SceneObject, ShapeSpec, Transform

RECIPE_VERSION = 'model-recipe-1.0'
INTERPRETER_VERSION = 'model-recipe-compiler-1.1'
SUPPORTED_INTERPRETERS = ('model-recipe-compiler-1.0', INTERPRETER_VERSION)
KINDS = ('bed', 'wardrobe', 'desk', 'chair', 'sofa', 'dining_table', 'storage', 'unknown', 'rack', 'pallet_stack')
MATERIALS = ('wood', 'white', 'dark', 'metal', 'cloth', 'linen', 'blue', 'cream')
_NAME = re.compile(r'^[a-z][a-z0-9_]{0,23}$')
MAX_PARTS = 128


class ModelRecipeError(ValueError):
    def __init__(self, code, path='$', detail=''):
        self.code, self.path, self.detail = code, path, detail
        super().__init__(code + ':' + path + (': ' + detail if detail else ''))


def _object(value, keys, path):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ModelRecipeError('MODEL_RECIPE_FIELDS_INVALID', path)


def _finite(value, path):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 10000:
        raise ModelRecipeError('MODEL_RECIPE_NUMBER_INVALID', path)
    return float(value)


def expression(value, parameters, *, index=None, depth=0, nodes=None):
    """A finite arithmetic grammar; no eval, imports, attributes or recursion."""
    nodes = [0] if nodes is None else nodes
    nodes[0] += 1
    if depth > 8 or nodes[0] > 128:
        raise ModelRecipeError('MODEL_RECIPE_EXPRESSION_BUDGET')
    if type(value) in (int, float):
        return _finite(value, '$.expression')
    if isinstance(value, str):
        if value == 'index' and index is not None:
            return index
        if value not in parameters:
            raise ModelRecipeError('MODEL_RECIPE_PARAMETER_UNKNOWN', '$.expression', value[:40])
        return _finite(parameters[value], '$.expression')
    _object(value, ('op', 'args'), '$.expression')
    if value['op'] not in ('add', 'sub', 'mul', 'div', 'min', 'max'):
        raise ModelRecipeError('MODEL_RECIPE_OPERATOR_INVALID')
    args = value['args']
    if not isinstance(args, list) or len(args) != 2:
        raise ModelRecipeError('MODEL_RECIPE_ARITY_INVALID')
    a, b = (expression(v, parameters, index=index, depth=depth+1, nodes=nodes) for v in args)
    if value['op'] == 'div' and abs(b) < 1e-10:
        raise ModelRecipeError('MODEL_RECIPE_DIVISION_BY_ZERO')
    result = {'add': lambda: a+b, 'sub': lambda: a-b, 'mul': lambda: a*b,
              'div': lambda: a/b, 'min': lambda: min(a,b), 'max': lambda: max(a,b)}[value['op']]()
    return _finite(result, '$.expression.result')


def recipe_schema(*, include_legacy=False):
    """Host-owned finite response grammar. Bounds are independently checked."""
    expr = {'anyOf': [{'type': 'number'}, {'type': 'string', 'maxLength': 24}]}
    for _ in range(5):
        expr = {'anyOf': [{'type': 'number'}, {'type': 'string', 'maxLength': 24},
            {'type': 'object', 'additionalProperties': False, 'required': ['op','args'],
             'properties': {'op': {'enum': ['add','sub','mul','div','min','max']},
                'args': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': expr}}}]}
    vec = {'type': 'array', 'minItems': 3, 'maxItems': 3, 'items': expr}
    parameter = {'type': 'object', 'additionalProperties': False,
        'required': ['name','type','minimum','maximum','default'], 'properties': {
            'name': {'type': 'string', 'pattern': _NAME.pattern},
            'type': {'enum': ['number','integer']}, 'minimum': {'type': 'number'},
            'maximum': {'type': 'number'}, 'default': {'type': 'number'}}}
    part = {'type': 'object', 'additionalProperties': False,
        'required': ['id','center','size','material','support_top','repeat'], 'properties': {
            'id': {'type': 'string', 'pattern': _NAME.pattern}, 'center': vec, 'size': vec,
            'material': {'enum': list(MATERIALS)}, 'support_top': {'type': 'boolean'},
            'repeat': {'anyOf': [{'type': 'null'}, {'type': 'string', 'maxLength': 24}]}}}
    return {'type': 'object', 'additionalProperties': False,
        'required': ['schema_version','interpreter_version','title','family','kind','parameters','parts'],
        'properties': {'schema_version': {'const': RECIPE_VERSION},
            'interpreter_version': {'enum': list(SUPPORTED_INTERPRETERS)} if include_legacy else {'const': INTERPRETER_VERSION},
            'title': {'type': 'string', 'minLength': 1, 'maxLength': 100},
            'family': {'enum': ['home','warehouse','common']}, 'kind': {'enum': list(KINDS)},
            'parameters': {'type': 'array', 'minItems': 3, 'maxItems': 6, 'items': parameter},
            'parts': {'type': 'array', 'minItems': 1, 'maxItems': 64, 'items': part}}}


def checked_recipe(value, *, sample=True):
    _object(value, ('schema_version','interpreter_version','title','family','kind','parameters','parts'), '$')
    if value['schema_version'] != RECIPE_VERSION or value['interpreter_version'] not in SUPPORTED_INTERPRETERS:
        raise ModelRecipeError('MODEL_RECIPE_VERSION_UNSUPPORTED')
    if (not isinstance(value['title'], str) or not 1 <= len(value['title'].strip()) <= 100
            or value['family'] not in ('home','warehouse','common') or value['kind'] not in KINDS):
        raise ModelRecipeError('MODEL_RECIPE_METADATA_INVALID')
    try:
        raw = json.dumps(value, allow_nan=False, ensure_ascii=False).encode('utf-8')
    except (ValueError, TypeError):
        raise ModelRecipeError('MODEL_RECIPE_JSON_INVALID') from None
    if len(raw) > 65536:
        raise ModelRecipeError('MODEL_RECIPE_PAYLOAD_BUDGET')
    definitions = value['parameters']
    if not isinstance(definitions, list) or not 3 <= len(definitions) <= 6:
        raise ModelRecipeError('MODEL_RECIPE_PARAMETERS_INVALID')
    seen = set()
    for row in definitions:
        _object(row, ('name','type','minimum','maximum','default'), '$.parameters')
        name = row['name']
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen or name == 'index':
            raise ModelRecipeError('MODEL_RECIPE_PARAMETER_NAME_INVALID')
        seen.add(name)
        low, high, default = (_finite(row[k], '$.parameters.'+name) for k in ('minimum','maximum','default'))
        if row['type'] not in ('number','integer') or not 0 < low <= default <= high <= 10:
            raise ModelRecipeError('MODEL_RECIPE_PARAMETER_RANGE_INVALID', '$.parameters.'+name)
        if row['type'] == 'integer' and any(type(row[k]) is not int for k in ('minimum','maximum','default')):
            raise ModelRecipeError('MODEL_RECIPE_INTEGER_INVALID', '$.parameters.'+name)
    if not {'width','depth','height'} <= seen or any(
            r['type'] != 'number' for r in definitions if r['name'] in ('width','depth','height')):
        raise ModelRecipeError('MODEL_RECIPE_ENVELOPE_REQUIRED')
    parts = value['parts']
    if not isinstance(parts, list) or not 1 <= len(parts) <= 64:
        raise ModelRecipeError('MODEL_RECIPE_PARTS_INVALID')
    part_ids = set()
    for part in parts:
        _object(part, ('id','center','size','material','support_top','repeat'), '$.parts')
        if (not isinstance(part['id'], str) or not _NAME.fullmatch(part['id']) or part['id'] in part_ids
                or part['material'] not in MATERIALS or type(part['support_top']) is not bool
                or any(not isinstance(part[k], list) or len(part[k]) != 3 for k in ('center','size'))):
            raise ModelRecipeError('MODEL_RECIPE_PART_INVALID')
        part_ids.add(part['id'])
        if part['repeat'] is not None and not any(r['name'] == part['repeat'] and r['type'] == 'integer' for r in definitions):
            raise ModelRecipeError('MODEL_RECIPE_REPEAT_INVALID')
    result = deepcopy(value)
    if sample:
        # Defaults and domain corners only; every actual instance is rechecked.
        samples = [dict((p['name'], p['default']) for p in definitions)]
        samples += [dict(zip((p['name'] for p in definitions), values)) for values in
            product(*[(p['minimum'],p['maximum']) for p in definitions])]
        for parameters in samples:
            compiled_parts(result, parameters, already_checked=True)
    return result


def checked_parameters(recipe, parameters):
    if not isinstance(parameters, dict) or set(parameters) != {p['name'] for p in recipe['parameters']}:
        raise ModelRecipeError('MODEL_RECIPE_INSTANCE_PARAMETERS_INVALID')
    for row in recipe['parameters']:
        value = parameters[row['name']]
        number = _finite(value, '$.parameters.'+row['name'])
        if not row['minimum'] <= number <= row['maximum'] or row['type'] == 'integer' and type(value) is not int:
            raise ModelRecipeError('MODEL_RECIPE_INSTANCE_RANGE_INVALID', '$.parameters.'+row['name'])
    return deepcopy(parameters)


def compiled_parts(recipe, parameters, *, already_checked=False):
    recipe = recipe if already_checked else checked_recipe(recipe, sample=False)
    parameters = checked_parameters(recipe, parameters)
    envelope = [parameters[k] for k in ('width','depth','height')]
    output, identifiers = [], set()
    for template in recipe['parts']:
        count = 1 if template['repeat'] is None else parameters[template['repeat']]
        if type(count) is not int or not 1 <= count <= 10 or len(output)+count > MAX_PARTS:
            raise ModelRecipeError('MODEL_RECIPE_PART_BUDGET')
        for index in range(count):
            identity = template['id'] + ('_'+str(index) if template['repeat'] is not None else '')
            if identity in identifiers or len(identity) > 31:
                raise ModelRecipeError('MODEL_RECIPE_COMPILED_ID_INVALID')
            if recipe['kind']=='unknown' and identity=='keepout':
                raise ModelRecipeError('MODEL_RECIPE_RESERVED_PART_ID', '$.parts.'+identity)
            identifiers.add(identity)
            centre, size = [tuple(expression(v, parameters, index=index if template['repeat'] else None) for v in template[k])
                            for k in ('center','size')]
            if any(not .002 <= v <= 10 for v in size):
                raise ModelRecipeError('MODEL_RECIPE_PART_SIZE_INVALID', '$.parts.'+identity,
                    json.dumps(dict(parameters=parameters,actual_size_m=list(size),allowed_size_m=[.002,10]),separators=(',',':')))
            bounds = [(centre[i]-size[i]/2,centre[i]+size[i]/2) for i in range(3)]
            allowed = [(-envelope[0]/2,envelope[0]/2),(-envelope[1]/2,envelope[1]/2),(0,envelope[2])]
            if any(a < lo-1e-7 or b > hi+1e-7 for (a,b),(lo,hi) in zip(bounds,allowed)):
                violations=[dict(axis='xyz'[i],actual_m=list(bounds[i]),allowed_m=list(allowed[i]))
                    for i in range(3) if bounds[i][0]<allowed[i][0]-1e-7 or bounds[i][1]>allowed[i][1]+1e-7]
                raise ModelRecipeError('MODEL_RECIPE_PART_OUTSIDE_ENVELOPE', '$.parts.'+identity,
                    json.dumps(dict(parameters=parameters,violations=violations),separators=(',',':')))
            if template['support_top'] and (size[2] > min(size[:2])*.5 or min(size[:2]) < .04):
                raise ModelRecipeError('MODEL_RECIPE_SUPPORT_NOT_HORIZONTAL_SURFACE', '$.parts.'+identity,
                    json.dumps(dict(parameters=parameters,actual_size_m=list(size),
                        maximum_thickness_m=min(size[:2])*.5,minimum_horizontal_extent_m=.04),separators=(',',':')))
            output.append(dict(id=identity,center=list(centre),size=list(size),material=template['material'],
                support_top=template['support_top']))
    # A floor-standing recipe cannot float. Junction overlap within an assembly
    # is allowed; independent instances/children still use collision checks.
    if min(p['center'][2]-p['size'][2]/2 for p in output) > .001:
        raise ModelRecipeError('MODEL_RECIPE_FLOATING_ASSEMBLY')
    if recipe['interpreter_version']==INTERPRETER_VERSION:
        checked_assembly(output,parameters)
    return output


def checked_assembly(parts, parameters):
    """Basic connected floor load path, not strength/physical certification.

    Preserve old compiler snapshots on replay; new definitions and new reuse
    must not turn one grounded leg into permission for unrelated floating parts.
    """
    boxes=[[(p['center'][i]-p['size'][i]/2,p['center'][i]+p['size'][i]/2)
            for i in range(3)] for p in parts]
    linked={i for i,b in enumerate(boxes) if b[2][0]<=.001}
    def connected(a,b):
        overlap=[min(a[k][1],b[k][1])-max(a[k][0],b[k][0]) for k in range(3)]
        return all(v>=-1e-7 for v in overlap) and sum(v>1e-7 for v in overlap)>=2
    while True:
        more={i for i,b in enumerate(boxes) if i not in linked and any(
            connected(b,boxes[j]) for j in linked)}
        if not more:break
        linked|=more
    if len(linked)!=len(parts):
        raise ModelRecipeError('MODEL_RECIPE_DISCONNECTED_PARTS','$.parts',json.dumps(dict(
            parameters=parameters,disconnected_ids=[p['id'] for i,p in enumerate(parts) if i not in linked],
            requirement='Every rigid part must touch/intersect a part connected to the floor.'),separators=(',',':')))
    actual=[max(b[i][1] for b in boxes)-min(b[i][0] for b in boxes) for i in range(3)]
    expected=[parameters[k] for k in ('width','depth','height')]
    if any(abs(a-e)>.001 for a,e in zip(actual,expected)):
        raise ModelRecipeError('MODEL_RECIPE_DIMENSION_ENVELOPE_MISMATCH','$.parts',json.dumps(dict(
            parameters=parameters,actual_size_m=actual,requested_size_m=expected),separators=(',',':')))


def recipe_reuse_problem(recipe):
    """Old snapshots remain readable; independently recheck their reuse today."""
    try:
        definitions=recipe['parameters']
        samples=[{p['name']:p['default'] for p in definitions}]
        samples += [dict(zip((p['name'] for p in definitions),values)) for values in
            product(*[(p['minimum'],p['maximum']) for p in definitions])]
        for parameters in samples:checked_assembly(compiled_parts(recipe,parameters),parameters)
    except ModelRecipeError as error:return str(error)
    return None


def recipe_digest(recipe):
    from .revisions import canonical_sha256
    return canonical_sha256(checked_recipe(recipe, sample=False))


def recipe_model_id(recipe):
    return 'local.'+recipe_digest(recipe)[:24]


def recipe_support_names(recipe):
    """Enumerate declared names without inventing an instance's geometry.

    A repeated surface may not exist at a smaller actual count. The instance
    support lookup still compiles and verifies that exact count before use.
    """
    recipe = checked_recipe(recipe, sample=False)
    maxima = {p['name']:p['maximum'] for p in recipe['parameters']}
    return [part['id'] + ('_'+str(index) if part['repeat'] else '')
        for part in recipe['parts'] if part['support_top']
        for index in range(maxima[part['repeat']] if part['repeat'] else 1)]


def recipe_manifest(recipe):
    recipe = checked_recipe(recipe)
    defaults = {p['name']:p['default'] for p in recipe['parameters']}
    parts = compiled_parts(recipe, defaults, already_checked=True)
    reuse_problem=recipe_reuse_problem(recipe)
    return dict(model_id=recipe_model_id(recipe), recipe_sha256=recipe_digest(recipe), title=recipe['title'],
        kind=recipe['kind'], family=recipe['family'], environments=[recipe['family']] if recipe['family'] != 'common' else ['home','warehouse'],
        tool='place_model_recipe',catalog_version=RECIPE_VERSION,interpreter_version=recipe['interpreter_version'],
        dimensions_m=dict(default=[defaults[k] for k in ('width','depth','height')],
            minimum=[next(p['minimum'] for p in recipe['parameters'] if p['name']==k) for k in ('width','depth','height')],
            maximum=[next(p['maximum'] for p in recipe['parameters'] if p['name']==k) for k in ('width','depth','height')]),
        parameters=deepcopy(recipe['parameters']), variants=['standard'], finishes=['recipe_materials'],
        support_parts=[p['id'] for p in parts if p['support_top']], status='geometry_sampled' if not reuse_problem else 'legacy_geometry_needs_revision',
        reusable=not bool(reuse_problem), reuse_problem=reuse_problem,
        placement_relations=['floor'],risk='unknown' if recipe['kind']=='unknown' else 'collision',
        validation_scope='default_and_parameter_corners; each_instance_rechecked; photo_and_physical_unverified')


def checked_recipe_arguments(args):
    _object(args, ('id','kind','model_id','recipe_sha256','interpreter_version','recipe','parameters','center_m','yaw_deg'), '$.arguments')
    recipe = checked_recipe(args['recipe'], sample=False)
    if (args['kind'] != recipe['kind'] or args['model_id'] != recipe_model_id(recipe)
            or args['recipe_sha256'] != recipe_digest(recipe) or args['interpreter_version'] != recipe['interpreter_version']):
        raise ModelRecipeError('MODEL_RECIPE_BINDING_MISMATCH')
    if not isinstance(args['id'], str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', args['id']):
        raise ModelRecipeError('MODEL_RECIPE_INSTANCE_ID_INVALID')
    if not isinstance(args['center_m'], (list,tuple)) or len(args['center_m']) != 2:
        raise ModelRecipeError('MODEL_RECIPE_INSTANCE_POSITION_INVALID')
    for v in args['center_m']:
        _finite(v, '$.center_m')
        if abs(v)>20:raise ModelRecipeError('MODEL_RECIPE_INSTANCE_POSITION_INVALID')
    yaw = _finite(args['yaw_deg'], '$.yaw_deg')
    if not -180 <= yaw <= 180:raise ModelRecipeError('MODEL_RECIPE_INSTANCE_YAW_INVALID')
    return recipe, compiled_parts(recipe, args['parameters'], already_checked=True)


def expand_model_recipe(args):
    _, parts = checked_recipe_arguments(args)
    angle=math.radians(args['yaw_deg']);co,si=math.cos(angle),math.sin(angle)
    x,y=args['center_m']
    objects=tuple(SceneObject(args['id']+'_'+p['id'],'equipment',
        Transform((x+co*p['center'][0]-si*p['center'][1],y+si*p['center'][0]+co*p['center'][1],p['center'][2]),
                  (0.,0.,float(args['yaw_deg']))),ShapeSpec('box',tuple(p['size']))) for p in parts)
    if args['kind']=='unknown':
        from .room_items import KEEP_OUT_MARGIN_M
        size=args['parameters']
        objects+=(SceneObject(args['id']+'_keepout','equipment',
            Transform((float(x),float(y),.175),(0.,0.,float(args['yaw_deg']))),
            ShapeSpec('box',(float(size['width'])+2*KEEP_OUT_MARGIN_M,
                float(size['depth'])+2*KEEP_OUT_MARGIN_M,.35))),)
    return objects


def recipe_support_surface(parent, part):
    _, parts = checked_recipe_arguments(parent)
    if not any(p['id']==part and p['support_top'] for p in parts):return None
    return next(p for p in expand_model_recipe(parent) if p.id==parent['id']+'_'+part)


def recipe_support_parts(recipe, parameters=None):
    recipe=checked_recipe(recipe,sample=False)
    parameters=parameters or {p['name']:p['default'] for p in recipe['parameters']}
    return [p['id'] for p in compiled_parts(recipe,parameters,already_checked=True) if p['support_top']]


def recipe_display_meshes(args):
    from .room_visuals import Meshes
    _,parts=checked_recipe_arguments(args)
    # Geometry is identical to the compiler, with rounded display edges only.
    mesh=Meshes((1.,1.,1.))
    for p in parts:mesh.box(p['id'],p['center'],p['size'],p['material'],.005)
    return mesh.parts
