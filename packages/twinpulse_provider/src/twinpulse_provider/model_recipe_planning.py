# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Audited scene-stage library reuse/synthesis; no independent HTTP client."""
from copy import deepcopy
from twinpulse_core.model_library import library_models
from twinpulse_core.model_recipe import (KINDS, recipe_schema, checked_recipe, recipe_model_id,
    recipe_manifest, ModelRecipeError)
from twinpulse_core.warehouse_models import support_parts
from .scene_contract import SceneContractError, report, issue


# Shared by initial definition and diagnostic-bound replacement. The compiler,
# not these examples or the model verdict, remains the acceptance authority.
MODEL_RECIPE_AUTHORING_INSTRUCTIONS = (
    'PREFER authoring_version=proportional-boxes-1.0 for new models: return title/family/kind, '
    'exactly three number parameters width/depth/height, and parts with id, x_bounds, y_bounds, '
    'z_bounds, material and support_top. Bounds are normalized [min,max] with min < max: '
    'x/y in [-0.5,0.5] of width/depth, z in [0,1] of height. Host computes centre/size expressions. '
    'Example a full-width top panel: x_bounds=[-0.5,0.5], y_bounds=[-0.5,0.5], z_bounds=[0.96,1]. '
    'Every declared dimension must include ALL parts, including a headboard/back or legs. '
    'Preserve real openings and usable thin support panels, connected to the floor. '
    'This notation supports resizing but not repeated-count parameters. '
    'The legacy expression notation below is accepted for compatibility, not preferred. '
    'Author data-only axis-aligned box assemblies, never Python or tools. '
    'Required number parameters are width/depth/height; all parameter minima are strictly positive. '
    'Optional bounded integer repeat counts start at 1, not 0. Omit unused count parameters. '
    'Expressions are numbers, parameter-name strings, or binary '
    '{op:add/sub/mul/div/min/max,args:[a,b]}. For example size:["width","depth",0.02] '
    'and centre z:{"op":"sub","args":["height",0.01]}. Never replace an unknown size with 0+0. '
    'Local x/y are centred: x lies in [-width/2,width/2], y in [-depth/2,depth/2]; '
    'z lies in [0,height]. A full-width centred panel has x=0, not width/2. '
    'Every part has positive size at the default, every min/max corner, and the actual instance. '
    'Every box side is at least 0.002m. For support_top=true BOTH horizontal extents '
    'must be at least 0.04m and thickness <= half of EACH horizontal extent at ALL tested dimensions. '
    'Depth is the full front-to-back assembly extent, not the thickness of a vertical back panel. '
    'Choose parameter domains that can represent the observed elongated shape as well as the default. '
    'An object long along local Y needs a sufficient depth domain; rotating its yaw cannot enlarge that domain. '
    'Place back/side panels on the evidenced side of the local assembly, not a side inferred from kind alone. '
    'A vertical back is not a horizontal shelf. Choose default AND minimum dimensions that '
    'provide real support for the supplied current child footprint estimates. '
    'Use proportional shelf elevations and thin panels that fit the entire declared range. '
    'Actual assembled width/depth/height must equal those parameters, not merely fit inside. '
    'All rigid parts must touch/intersect a positive-area chain connected to the floor; '
    'an upper panel need not directly touch the floor, but floating disconnected parts fail. '
    'Opposite posts/panels need opposite signed centres. A repeated part uses repeat=integer parameter name '
    'and may use index starting at zero. support_top=true only for usable actual horizontal panels. '
    'Separate panels create real open interiors; a solid block or an open style name does not create shelves. '
    'Read validation.detail tested parameters and actual/allowed bounds when correcting an error. '
    'Keep the observed shape; do not add shelves or parts not supported by the request/evidence. '
    'Do not embed room coordinates, personal photo names, source prompts or measured claims. '
    'This bounded floor-furniture recipe does not provide cloth drape or articulated mechanisms. '
    'A local recipe instance uses variant=standard and finish=recipe_materials; its exact '
    'recipe_parameters width/depth/height equal dimensions_m, with all other declared parameters supplied. '
    'Builtin instances instead use their manifest variant/finish and null recipe_parameters. '
)


def definition_context(draft, observation, identity):
    """Frozen support demand, without turning a plan estimate into observation."""
    selected={identity};inventory={r['id']:r for r in draft['inventory']}
    by_ref={ref:r['id'] for r in draft['inventory'] for ref in r['source']['observation_ids']}
    while True:
        before=set(selected)
        selected.update(i for i,v in draft['objects'].items() if v['placement']['parent_id'] in selected)
        for relation in observation.relations:
            if (relation['relation'] in ('on','supported_by','attached_to','inside') and
                    by_ref.get(relation['object_id']) in selected and relation['subject_id'] in by_ref):
                selected.add(by_ref[relation['subject_id']])
        if selected==before:break
    objects={i:deepcopy(draft['objects'][i]) for i in sorted(selected) if i in draft['objects']}
    demands=[dict(id=i,dimensions_m=deepcopy(v['dimensions_m']),yaw_deg=v['yaw_deg'],
        placement=deepcopy(v['placement']),basis='current_plan_estimate_not_verified_support')
        for i,v in objects.items() if i!=identity and v['placement']['relation']=='surface']
    return dict(target=deepcopy(inventory[identity]),
        related_inventory=[deepcopy(inventory[i]) for i in sorted(selected)],
        prepared_objects=objects,pending_object_ids=sorted(selected-set(objects)),
        current_support_demands=demands,
        evidence_status='Current plan/dimensions are estimates, not measurements or observed support facts.',
        source_target_ids=sorted(selected))


def recipe_issue(error, path, identity):
    import json
    numeric=None
    try:numeric=json.loads(error.detail)
    except (ValueError,TypeError):pass
    return issue(error.code,path+error.path[1:],target_ids=[identity],detail=error.detail,
        **({'numerical_diagnosis':numeric} if isinstance(numeric,dict) else {}))


def definition_schema(kind, children):
    recipe=single_recipe_schema(kind)
    if not children:return recipe
    return dict(type='object',additionalProperties=False,required=['recipe','support_bindings'],properties=dict(
        recipe=recipe,support_bindings=dict(type='object',additionalProperties=False,required=list(children),
            properties={i:dict(type='string',minLength=1,maxLength=32) for i in children})))


def checked_definition(value, kind, identity, children):
    from .semantic_scene import _shape_issues
    from twinpulse_core.model_recipe import compiled_parts
    problems=_shape_issues(value,definition_schema(kind,children))
    if problems:raise SceneContractError(report(problems))
    recipe=checked_single_recipe(value['recipe'] if children else value,kind,identity)
    bindings=value['support_bindings'] if children else {}
    parts=[p['id'] for p in compiled_parts(recipe,{p['name']:p['default'] for p in recipe['parameters']})
        if p['support_top']]
    problems=[issue('MODEL_DEFINITION_SUPPORT_BINDING_INVALID','$.support_bindings.'+child,
        target_ids=[identity,child],actual=part,expected={'support_parts':parts})
        for child,part in bindings.items() if part not in parts]
    if problems:raise SceneContractError(report(problems))
    return recipe,deepcopy(bindings)


def available_models(snapshots):
    from .assembly_evidence import describe,recipe_descriptor
    builtin=[dict(m,support_parts=list(support_parts(m['kind']))) for m in library_models()]
    from twinpulse_core.model_library import parametric_parts
    for model in builtin:
        if model['tool']=='place_furniture':
            parts=[dict(id=i,center_m=[x,y,z+h/2],size_m=[w,d,h],support_top=i in model['support_parts'])
                for i,x,y,z,w,d,h in parametric_parts(dict(kind=model['kind'],
                    dimensions_m=model['dimensions_m']['default'],variant=model['variants'][0],finish=model['finishes'][0]))]
            model['assembly_geometry']=describe(parts,model['dimensions_m']['default'],
                binding=dict(model_id=model['model_id'],catalog_version=model['catalog_version']))
    generated=[m for v in snapshots.values() if (m:=recipe_manifest(v))['reusable']]
    for model in generated:
        recipe=snapshots[model['model_id']]
        model['assembly_geometry']=recipe_descriptor(recipe,{p['name']:p['default'] for p in recipe['parameters']})
    return builtin+generated


def resolution_schema(draft, snapshots):
    rows=available_models(snapshots);slots={}
    for row in draft['inventory']:
        if row['kind'] not in KINDS or row['id'] in draft['objects']:continue
        ids=[m['model_id'] for m in rows if m['kind']==row['kind']]
        schema=recipe_schema();schema['properties']['kind']={'const':row['kind']}
        slots[row['id']]={'anyOf':[
            dict(type='object',additionalProperties=False,required=['model_id'],properties={'model_id':{'enum':ids}}),
            dict(type='object',additionalProperties=False,required=['recipe'],properties={'recipe':schema})]}
    return dict(type='object',additionalProperties=False,required=list(slots),properties=slots)


def checked_resolution(value,draft,snapshots):
    from .semantic_scene import _shape_issues
    problems=_shape_issues(value,resolution_schema(draft,snapshots),'$.model_resolution')
    if problems:raise SceneContractError(report(problems))
    result=deepcopy(draft);recipes=deepcopy(snapshots)
    selected={i:v['model_id'] for i,v in draft['objects'].items()};created=[]
    for identity,row in value.items():
        if 'recipe' in row:
            try:recipe=checked_recipe(row['recipe'])
            except ModelRecipeError as error:
                raise SceneContractError(report([issue(error.code,'$.model_resolution.'+identity+'.recipe'+error.path[1:],
                    target_ids=[identity],detail=error.detail)])) from error
            model=recipe_model_id(recipe)
            if model not in recipes:created.append(model)
            recipes[model]=recipe
        else:model=row['model_id']
        selected[identity]=model
    result['model_recipes']=recipes
    result['model_selections']=selected
    result['model_resolution_done']=True
    return result,created


def floor_recipe_allowed(row, observation=None):
    """Unknown identity is not evidence for inventing floor furniture.

    Preserve its existing conservative common.unknown surface/floor proxy.
    Explicit text objects and typed observed floor support can request recipes;
    names, descriptions, image hashes and 'inside' are never floor authority.
    """
    if row['kind']!='unknown':return True
    refs=set(row['source']['observation_ids'])
    if not refs:return row['source']['basis']=='user'
    if observation is None:return False
    from .scene_contract import role_of
    floors={r['id'] for r in observation.entities if
        r.get('category')=='floor' and role_of(r)=='structure'}
    return any(r['subject_id'] in refs and r['object_id'] in floors and
        r['relation'] in ('on','supported_by') for r in observation.relations)


def selection_schema(draft, snapshots, targets, observation=None):
    """Small discovery call; do not repeat an expression grammar per furniture."""
    rows=available_models(snapshots);kinds={r['id']:r['kind'] for r in draft['inventory']}
    if not targets or len(set(targets))!=len(targets) or any(kinds.get(i) not in KINDS for i in targets):
        raise ValueError('MODEL_SELECTION_TARGET_INVALID')
    by_id={r['id']:r for r in draft['inventory']}
    slots={}
    for identity in targets:
        permitted=floor_recipe_allowed(by_id[identity],observation)
        choices=[m['model_id'] for m in rows if m['kind']==kinds[identity] and
            (permitted or m['model_id']=='common.unknown')]
        slots[identity]={'enum':choices+(['create_recipe'] if permitted else [])}
    return dict(type='object',additionalProperties=False,required=list(slots),properties=slots)


def checked_selection(value, draft, snapshots, targets, observation=None):
    from .semantic_scene import _shape_issues
    problems=_shape_issues(value,selection_schema(draft,snapshots,targets,observation),'$.model_selection')
    if problems:raise SceneContractError(report(problems))
    return deepcopy(value)


def single_recipe_schema(kind):
    from .model_recipe_authoring import authoring_schema
    return authoring_schema(kind)


def checked_single_recipe(value, kind, identity):
    from .semantic_scene import _shape_issues
    problems=_shape_issues(value,single_recipe_schema(kind),'$.recipe')
    if problems:raise SceneContractError(report(problems))
    from .model_recipe_authoring import compile_authoring
    try:return compile_authoring(value)
    except ModelRecipeError as error:
        raise SceneContractError(report([recipe_issue(error,'$.recipe',identity)])) from error


def restored_parameter_contract(draft, error):
    """Correct known saved cosmetic fields, never identity or frozen geometry.

    Older candidates could accept built-in variants for a local recipe. Only
    these explicit field errors may enter the carried repair budget. Every
    snapshot and all object selections remain pinned; no automatic migration.
    """
    import re
    from .semantic_scene import batch_schema,revision
    recipes=draft.get('model_recipes',{})
    for identity,recipe in recipes.items():
        checked_recipe(recipe,sample=False)
        if recipe_model_id(recipe)!=identity:raise ValueError('MODEL_RECIPE_BINDING_MISMATCH')
    slots={};properties=batch_schema(draft['inventory'],list(draft['objects']),recipes=recipes,
        selections=draft.get('model_selections'))['properties']
    for problem in error.contract_report.get('issues',[]):
        match=re.fullmatch(r'\$\.objects\.([A-Za-z][A-Za-z0-9_-]{0,31})\.(variant|finish)',problem.get('path',''))
        if (not match or problem['code'] not in {'SEMANTIC_CONSTANT_MISMATCH','SEMANTIC_ENUM_INVALID'}):return None
        identity,field=match.groups();value=draft['objects'].get(identity)
        if not value or value['model_id'] not in recipes:return None
        if draft.get('model_selections',{}).get(identity)!=value['model_id']:return None
        if recipes[value['model_id']]['kind']!=next(r['kind'] for r in draft['inventory'] if r['id']==identity):
            raise ValueError('MODEL_RECIPE_BINDING_MISMATCH')
        slots.setdefault(identity,{})[field]=properties[identity]['properties'][field]
    if not slots:return None
    return dict(type='object',additionalProperties=False,required=['base_revision','changes'],properties={
        'base_revision':{'const':revision(draft)},'changes':dict(type='object',additionalProperties=False,
            required=list(slots),properties={identity:dict(type='object',additionalProperties=False,
                required=list(fields),properties=fields) for identity,fields in slots.items()})})


def checked_restored_parameters(value,draft,schema):
    from .semantic_scene import _shape_issues,checked_batch
    problems=_shape_issues(value,schema)
    if problems:raise SceneContractError(report(problems))
    result=deepcopy(draft)
    for identity,fields in value['changes'].items():result['objects'][identity].update(deepcopy(fields))
    return checked_batch(result['objects'],{**result,'objects':{}},list(result['objects']))
