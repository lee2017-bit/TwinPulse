# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Diagnostic-bound parent model replacement, not arbitrary scene mutation."""
from copy import deepcopy

from twinpulse_core.model_recipe import KINDS, checked_recipe, recipe_model_id
from .model_recipe_planning import single_recipe_schema, available_models, floor_recipe_allowed,recipe_issue
from .scene_contract import SceneContractError, report, issue


def descendant_closure(draft, roots):
    identities=set(roots)
    while True:
        children={i for i,v in draft['objects'].items() if v['placement']['parent_id'] in identities}
        if children<=identities:return identities
        identities.update(children)


def capability_diagnosis(quality, progressive):
    """Do not let an unrelated layout hypothesis hide numerical support facts.

    Pure layout still calls for pose repair, not model replacement. In a mixed
    diagnosis only original numerical pending evidence can select a capability
    target; capability_targets then enforces the grounded parent/child scope.
    """
    layout=bool(quality.get('layout_hypotheses')) or any(row.get('code') in {
        'RENDER_LAYOUT_MISMATCH','PHOTO_RELATIVE_ORDER_CONTRADICTION',
        'PHOTO_OBSERVED_REGION_CONTRADICTION'} for row in quality.get('issues',[]))
    pending=[deepcopy(row['evidence']) for row in progressive.get('unresolved',[]) if row.get('evidence')]
    return {**quality,'issues':([] if layout else deepcopy(quality.get('issues',[])))+pending}


def binding_schema(draft, parent, children, direct_parts=None):
    """Frozen original closure; only direct surface children are editable."""
    kinds={r['id']:r['kind'] for r in draft['inventory']}
    closure=descendant_closure(draft,[parent])
    fields={}
    for child in children:
        original=({'enum':list(direct_parts)} if direct_parts is not None else
                  dict(type='string',minLength=1,maxLength=32))
        alternatives=[original]
        parents=sorted(i for i in closure if i!=child and kinds[i]!='unknown')
        if parents:
            alternatives.append(dict(type='object',additionalProperties=False,
                required=['parent_id','part','anchor'],properties=dict(parent_id={'enum':parents},
                    part=dict(type='string',minLength=1,maxLength=32),anchor={'const':'centre'})))
        fields[child]={'anyOf':alternatives}
    return dict(type='object',additionalProperties=False,required=children,properties=fields)


def capability_targets(draft, diagnosis, observation=None):
    """Only a current, numerical failed support permits replacing its parent."""
    kinds={r['id']:r['kind'] for r in draft['inventory']};result={}
    for problem in diagnosis.get('issues',[]):
        appearance=problem.get('code')=='RENDER_APPEARANCE_MISMATCH'
        if problem.get('code')!='PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE' and not appearance:continue
        actual=problem.get('actual') or {};expected=problem.get('expected') or {}
        if not appearance and actual.get('reason') not in {'SURFACE_CAPACITY_EXCEEDED','SUPPORT_CLEARANCE_EXCEEDED',
                'SUPPORT_SURFACE_UNAVAILABLE'}:continue
        if appearance and (expected.get('source') not in {'source_photo_and_current_render','user_request_and_current_render'} or
            not actual.get('frame_key') or (actual.get('render_assessment') or {}).get('confidence',0)<.8):continue
        parent=problem.get('target_ids',[None])[0] if appearance else expected.get('parent_id')
        if parent not in draft['objects'] or kinds.get(parent) not in KINDS:continue
        source_row=next(r for r in draft['inventory'] if r['id']==parent)
        if not floor_recipe_allowed(source_row,observation):continue
        if draft['objects'][parent]['placement']['relation']!='floor':continue
        if any(v['placement']['parent_id']==parent and v['placement']['relation']!='surface'
               for v in draft['objects'].values()):continue
        children=sorted(i for i,v in draft['objects'].items() if
            v['placement']['parent_id']==parent and v['placement']['relation']=='surface')
        if not appearance and (not children or not set(problem.get('target_ids',[])).intersection(children)):continue
        result[parent]=children
    return result


def capability_schema(draft, diagnosis, snapshots, observation=None):
    from .semantic_scene import revision
    targets=capability_targets(draft,diagnosis,observation);slots={}
    kinds={r['id']:r['kind'] for r in draft['inventory']}
    models=available_models(snapshots)
    for parent,children in targets.items():
        fields=dict(dimensions_m=dict(type='array',minItems=3,maxItems=3,
            items=dict(type='number',minimum=.001,maximum=10)),variant=dict(type='string',maxLength=32),
            finish=dict(type='string',maxLength=32),recipe_parameters={'anyOf':[{'type':'null'},
                dict(type='object',additionalProperties=dict(type='number'))]},
            support_bindings=binding_schema(draft,parent,children))
        branches=[]
        choices=[dict(model=dict(type='object',additionalProperties=False,required=['recipe'],
            properties={'recipe':single_recipe_schema(kinds[parent])}),variant={'const':'standard'},
            finish={'const':'recipe_materials'},recipe_parameters=dict(type='object',
                additionalProperties=dict(type='number')))]
        for model in models:
            if model['kind']!=kinds[parent]:continue
            if children and not model['support_parts']:continue
            bindings=binding_schema(draft,parent,children,model['support_parts'])
            choices.append(dict(model=dict(type='object',additionalProperties=False,required=['model_id'],
                properties={'model_id':{'const':model['model_id']}}),
                variant={'enum':model['variants']},finish={'enum':model['finishes']},
                recipe_parameters=(dict(type='object',additionalProperties=dict(type='number'))
                    if model['model_id'].startswith('local.') else {'type':'null'}),support_bindings=bindings))
        for choice in choices:
            bound={**deepcopy(fields),**choice}
            branches.append(dict(type='object',additionalProperties=False,required=list(bound),properties=bound))
        slots[parent]={'anyOf':[{'type':'null'},*branches]}
    return dict(type='object',additionalProperties=False,required=['base_revision','replacements'],properties={
        'base_revision':{'const':revision(draft)},'replacements':dict(type='object',additionalProperties=False,
            required=list(slots),properties=slots)})


def capability_prompt_context(draft, diagnosis, snapshots, observation=None):
    """Lossless relevant closure and factored diagnosis, not a new authority.

    Full state/diagnosis remain pinned and validated by checked_capability and
    the whole compiler. Only the model's read-only request context is compacted.
    """
    from twinpulse_core import canonical_sha256
    from .semantic_scene import revision
    targets=capability_targets(draft,diagnosis,observation)
    identities=descendant_closure(draft,targets)
    kinds={r['kind'] for r in draft['inventory'] if r['id'] in targets}
    models={v['model_id'] for i,v in draft['objects'].items() if i in identities}
    tables={}
    def factor(value):
        if isinstance(value,list):return [factor(v) for v in value]
        if not isinstance(value,dict):return deepcopy(value)
        result={}
        for key,item in value.items():
            if key=='support_options':
                digest=canonical_sha256(item);tables[digest]=deepcopy(item)
                result['support_options_ref']=digest
            else:result[key]=factor(item)
        return result
    compact=factor(diagnosis)
    return dict(base_revision=revision(draft),full_candidate_sha256=canonical_sha256(draft),
        validation_sha256=canonical_sha256(diagnosis),
        candidate_scope=('target floor parent models and original direct surface-child bindings only; '
            'an object binding may explicitly use a non-unknown support inside this original descendant closure; '
            'all other fields and objects unchanged'),
        candidate=dict(room=deepcopy(draft['room']),
            inventory=[deepcopy(r) for r in draft['inventory'] if r['id'] in identities],
            objects={i:deepcopy(draft['objects'][i]) for i in sorted(identities)},
            model_recipes={i:deepcopy(v) for i,v in draft.get('model_recipes',{}).items() if i in models}),
        validation=compact,support_options_tables=tables,
        available_models=[m for m in available_models(snapshots) if m['kind'] in kinds])


def capability_signature(draft, diagnosis, observation=None):
    """Rollback-independent identity; a changed child may warrant a new repair."""
    from twinpulse_core import canonical_sha256
    targets=capability_targets(draft,diagnosis,observation)
    identities=descendant_closure(draft,targets)
    models={draft['objects'][i]['model_id'] for i in identities}
    evidence=sorted((dict(code=p.get('code'),targets=sorted(p.get('target_ids',[])),
        parent=(p.get('expected') or {}).get('parent_id'),part=(p.get('expected') or {}).get('part'),
        reason=(p.get('actual') or {}).get('reason')) for p in diagnosis.get('issues',[])
        if (p.get('expected') or {}).get('parent_id') in targets or
            set(p.get('target_ids',[])).intersection(targets)),key=lambda p:str(p))
    return canonical_sha256(dict(objects={i:draft['objects'][i] for i in sorted(identities)},
        model_recipes={i:draft.get('model_recipes',{}).get(i) for i in sorted(models)},
        evidence=evidence))


def checked_capability(value, draft, diagnosis, snapshots, observation=None, *, allow_decline=False):
    """Stage an exact copy; whole geometry/grounding is checked by the caller."""
    from .semantic_scene import _shape_issues, checked_batch, revision
    problems=_shape_issues(value,capability_schema(draft,diagnosis,snapshots,observation))
    if problems:raise SceneContractError(report(problems))
    if allow_decline and all(row is None for row in value['replacements'].values()):
        return None,{}  # A typed decline is NOT a changed/valid scene proposal.
    result=deepcopy(draft);registry={m['model_id']:m for m in available_models(snapshots)}
    kinds={r['id']:r['kind'] for r in draft['inventory']};created={}
    result.setdefault('model_recipes',{})
    result.setdefault('model_selections',{})
    for parent,row in value['replacements'].items():
        if row is None:continue
        selection=row['model']
        if 'recipe' in selection:
            from .model_recipe_authoring import compile_authoring
            try:recipe=compile_authoring(selection['recipe'])
            except ValueError as error:
                from twinpulse_core.model_recipe import ModelRecipeError
                problem=(recipe_issue(error,'$.replacements.'+parent+'.model.recipe',parent)
                    if isinstance(error,ModelRecipeError) else issue('MODEL_RECIPE_INVALID',
                        '$.replacements.'+parent+'.model.recipe',target_ids=[parent],detail=str(error)))
                raise SceneContractError(report([problem])) from error
            model=recipe_model_id(recipe)
            if recipe['kind']!=kinds[parent]:raise SceneContractError(report([issue('MODEL_CAPABILITY_KIND_CHANGED',parent)]))
            result['model_recipes'][model]=deepcopy(recipe)
            if model not in snapshots:created[model]=recipe
        else:
            model=selection['model_id']
            if model not in registry or registry[model]['kind']!=kinds[parent]:
                raise SceneContractError(report([issue('MODEL_CAPABILITY_KIND_CHANGED',parent)]))
            if model in snapshots:result['model_recipes'][model]=deepcopy(snapshots[model])
        original=result['objects'][parent]
        original.update(model_id=model,dimensions_m=deepcopy(row['dimensions_m']),variant=row['variant'],
            finish=row['finish'])
        if model.startswith('local.'):
            original['recipe_parameters']=deepcopy(row['recipe_parameters'])
        else:
            if row['recipe_parameters'] is not None:
                raise SceneContractError(report([issue('MODEL_CAPABILITY_BUILTIN_PARAMETERS_INVALID',parent)]))
            if result['model_recipes'] or 'recipe_parameters' in original:original['recipe_parameters']=None
        result['model_selections'][parent]=model
        for child,binding in row['support_bindings'].items():
            support_parent=parent if isinstance(binding,str) else binding['parent_id']
            part=binding if isinstance(binding,str) else binding['part']
            support=result['objects'][support_parent];support_model=support['model_id']
            from twinpulse_core.model_recipe import compiled_parts
            allowed=([p['id'] for p in compiled_parts(result['model_recipes'][support_model],support['recipe_parameters'])
                      if p['support_top']] if support_model.startswith('local.') else registry[support_model]['support_parts'])
            if part not in allowed:
                raise SceneContractError(report([issue('MODEL_CAPABILITY_SUPPORT_BINDING_INVALID',
                    '$.replacements.'+parent+'.support_bindings.'+child,target_ids=[parent,child],
                    actual=part,expected={'support_parts':allowed})]))
            result['objects'][child]['placement'].update(parent_id=support_parent,part=part)
            if isinstance(binding,dict):result['objects'][child]['placement']['anchor']=binding['anchor']
    for identity in result['objects']:
        seen={identity};ancestor=result['objects'][identity]['placement']['parent_id']
        # Wall/ceiling structure IDs are legitimate non-object boundaries.
        # Unknown/missing parents still fail the ordinary checked_batch/compiler.
        while ancestor in result['objects']:
            if ancestor in seen:
                raise SceneContractError(report([issue('MODEL_CAPABILITY_SUPPORT_CYCLE',identity)]))
            seen.add(ancestor);ancestor=result['objects'][ancestor]['placement']['parent_id']
    # Identity, source, inventory, room, region, yaw and child dimensions remain
    # fixed. An explicit binding may change a direct surface child's parent
    # inside the original closure. Whole geometry/ancestor checks still follow.
    if result['objects']==draft['objects']:
        raise SceneContractError(report([issue('SEMANTIC_PATCH_NO_CHANGE','$.replacements')]))
    if result.get('model_recipes'):
        for item in result['objects'].values():
            if not item['model_id'].startswith('local.'):item.setdefault('recipe_parameters',None)
    result=checked_batch(result['objects'],{**result,'objects':{}},list(result['objects']))
    if revision(result)==revision(draft):
        raise SceneContractError(report([issue('SEMANTIC_PATCH_NO_CHANGE','$.replacements')]))
    return result,created
