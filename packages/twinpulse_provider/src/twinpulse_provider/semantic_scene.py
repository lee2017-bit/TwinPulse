# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Small request-local semantic scene, compiled by the existing library executor.

Models select inventory/parameters; the host joins call IDs and evidence. No
photo hashes, reviewed bedroom inventory, world poses or dimensions are injected.
Intermediate drafts never carry Build/Run/physical authority.
"""
from copy import deepcopy
import json
import re

from twinpulse_core import canonical_sha256, SiteToolPlan, execute_site_tool_plan
from .errors import InvalidProviderResponseError
from .photo_layout import (GROUNDING_REVISION, KINDS, REGIONS, _model_fields,
                           compile_layout, layout_schema)
from .scene_contract import ground_layout, source_schema, SceneContractError, report, issue
from .scene_capacity import SEMANTIC_PAYLOAD_BYTES, checked_payload_bytes

SEMANTIC_REVISION = 'semantic-scene-1.0'
PATCH_REVISION = 'semantic-patch-1.0'
COMPILER_REVISION = 'semantic-scene-compiler-1.8'
ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')


def _shape_issues(value, schema, path='$'):
    """Validate our host-owned finite schema subset, without new dependencies.

    This is not a general interpreter for arbitrary model-supplied schemas.
    Library semantics, sources, parents and geometry are independently compiled.
    """
    import math
    if 'const' in schema and value != schema['const']:
        return [issue('SEMANTIC_CONSTANT_MISMATCH', path)]
    if 'enum' in schema and value not in schema['enum']:
        return [issue('SEMANTIC_ENUM_INVALID', path)]
    if 'anyOf' in schema and not any(not _shape_issues(value, branch, path) for branch in schema['anyOf']):
        return [issue('SEMANTIC_VARIANT_INVALID', path)]
    kind = schema.get('type')
    if isinstance(kind, list):
        return [] if any(not _shape_issues(value, {**schema, 'type': branch}, path) for branch in kind) else [
            issue('SEMANTIC_FIELD_TYPE_INVALID', path)]
    matches = {'object': isinstance(value, dict), 'array': isinstance(value, list),
        'number': type(value) in (int, float) and math.isfinite(value), 'string': isinstance(value, str),
        'null': value is None, 'integer': type(value) is int, 'boolean': type(value) is bool}
    if kind and not matches.get(kind, False):
        return [issue('SEMANTIC_FIELD_TYPE_INVALID', path)]
    problems = []
    if kind == 'object':
        properties = schema.get('properties', {})
        missing = set(schema.get('required', []))-set(value)
        extras = set(value)-set(properties) if schema.get('additionalProperties') is False else set()
        problems.extend(issue('SEMANTIC_FIELD_MISSING', path+'.'+key) for key in sorted(missing))
        problems.extend(issue('SEMANTIC_FIELD_UNKNOWN', path+'.'+key) for key in sorted(extras))
        for key in set(value) & set(properties):
            problems.extend(_shape_issues(value[key], properties[key], path+'.'+key))
    elif kind == 'array':
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 100000):
            problems.append(issue('SEMANTIC_ARRAY_LENGTH_INVALID', path))
        for index, child in enumerate(value):
            problems.extend(_shape_issues(child, schema.get('items', {}), f'{path}[{index}]'))
    elif kind == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 100000):
            problems.append(issue('SEMANTIC_STRING_LENGTH_INVALID', path))
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            problems.append(issue('SEMANTIC_ID_INVALID', path))
    elif kind in ('number', 'integer'):
        if not schema.get('minimum', -float('inf')) <= value <= schema.get('maximum', float('inf')):
            problems.append(issue('SEMANTIC_NUMBER_RANGE_INVALID', path))
        if 'exclusiveMinimum' in schema and value <= schema['exclusiveMinimum']:
            problems.append(issue('SEMANTIC_NUMBER_RANGE_INVALID', path))
    return problems[:64]


def inventory_requirements(observation):
    """Request-local coverage, never a reviewed photo's fixed furniture list."""
    from .scene_contract import role_of
    return [{'observation_id': row['id'], 'category': row.get('category', 'unknown')}
            for row in observation.entities if role_of(row) in {'object', 'unknown'}]


def structure_schema(request, observation, *, bound=False):
    room = layout_schema(request.prompt)['properties']['room']
    fields = {'id': {'type': 'string', 'pattern': ID.pattern}, 'kind': {'enum': list(KINDS)},
              'source': source_schema(observation)}
    if bound:
        from .semantic_bindings import binding_fields
        fields = binding_fields(request, observation)
    return {'type': 'object', 'additionalProperties': False,
        'required': ['summary', 'room', 'inventory'], 'properties': {
        'summary': {'type': 'string', 'minLength': 1, 'maxLength': 240}, 'room': room,
        # The new wire contract binds one row to one observed object. Legacy
        # schemas remain readable for saved evidence, not current generation.
        'inventory': {'type': 'array', 'minItems': (len(inventory_requirements(observation)) if bound
            else (len(inventory_requirements(observation))+2)//3),
            'items': {'type': 'object', 'additionalProperties': False,
                      'required': list(fields), 'properties': fields}}}}


def checked_structure(value, request, observation, *, bound=False):
    checked_payload_bytes(value, SEMANTIC_PAYLOAD_BYTES, 'SEMANTIC_PAYLOAD_BUDGET_REACHED')
    if not isinstance(value, dict) or set(value) != {'summary', 'room', 'inventory'}:
        raise SceneContractError(report([issue('SEMANTIC_STRUCTURE_INVALID', '$')]))
    rows = value['inventory']
    issues = []
    if not isinstance(rows, list):
        raise SceneContractError(report([issue('SEMANTIC_INVENTORY_INVALID', '$.inventory')]))
    room = value['room']
    from .photo_layout import requested_size
    import math
    room_valid = (isinstance(room, dict) and set(room) == {'width_m', 'length_m', 'height_m'}
        and all(type(v) in (int, float) and math.isfinite(v) for v in room.values())
        and 2 <= room['width_m'] <= 12 and 2 <= room['length_m'] <= 12 and 1.8 <= room['height_m'] <= 4)
    if not room_valid:
        issues.append(issue('SEMANTIC_ROOM_INVALID', '$.room'))
    size = requested_size(request.prompt)
    if room_valid and size and tuple(room[k] for k in ('width_m', 'length_m')) != size:
        issues.append(issue('EXPLICIT_ROOM_DIMENSIONS_CHANGED', '$.room'))
    if not isinstance(value['summary'], str) or not 1 <= len(value['summary']) <= 240:
        issues.append(issue('SEMANTIC_SUMMARY_INVALID', '$.summary'))
    if bound or (rows and any(isinstance(row, dict) and 'evidence_ref' in row for row in rows)):
        from .semantic_bindings import bind_inventory
        value = deepcopy(value)
        try:
            value['inventory'] = rows = bind_inventory(rows, request, observation)
        except SceneContractError as error:
            raise SceneContractError(report(issues+error.contract_report['issues'], ['grounding', 'compile'])) from error
    ids = set()
    entity_issues = []
    for index, row in enumerate(rows):
        path = f'$.inventory[{index}]'
        if (not isinstance(row, dict) or set(row) != {'id', 'kind', 'source'}
                or not isinstance(row.get('id'), str) or not ID.fullmatch(row['id'])
                or row['id'] in ids or row.get('kind') not in KINDS):
            entity_issues.append(issue('SEMANTIC_ENTITY_INVALID', path))
        else:
            ids.add(row['id'])
    if entity_issues:
        raise SceneContractError(report(issues+entity_issues, ['grounding', 'compile']))
    # Exact request-local user quotes and visual coverage are checked now,
    # before spending calls on parameters for an invalid inventory.
    try:
        ground_layout({'layout_version': GROUNDING_REVISION, 'summary': value['summary'],
            'room': value['room'], 'objects': rows}, observation, request)
    except SceneContractError as error:
        # The grounding adapter uses objects; feedback must name the actual
        # structure wire contract, not tell a model to add a forbidden field.
        diagnosis = deepcopy(error.contract_report)
        for item in diagnosis.get('issues', []):
            path = item.get('path', '')
            if path == '$.objects' or path.startswith('$.objects[') or path.startswith('$.objects.'):
                item['path'] = '$.inventory'+path[len('$.objects'):]
        issues.extend(diagnosis['issues'])
    if issues:
        raise SceneContractError(report(issues, ['compile']))
    return deepcopy(value)


def batch_schema(inventory, identities, *, recipes=None, selections=None):
    by_id = {row['id']: row for row in inventory}
    slots = {}
    for identity in identities:
        row = by_id[identity]
        from twinpulse_core.warehouse_models import WAREHOUSE_KINDS
        fields = {'region': {'type': 'string', 'enum': list(REGIONS)}, 'yaw_deg': {'type': 'number',
            'enum': [0] if row['kind'] in WAREHOUSE_KINDS else [0, 90, -90, 180]},
            **_model_fields(row['kind'], allowed_parents={i: r['kind'] for i, r in by_id.items() if i != identity},
                recipes=recipes, parent_models=selections)}
        if selections and identity in selections:
            selected=selections[identity]
            fields['model_id']={'const':selected}
            recipe=(recipes or {}).get(selected)
            if recipe:
                fields.pop('warehouse_parameters',None)
                fields['yaw_deg']={'type':'number','enum':[0,90,-90,180]}
                fields['variant']={'const':'standard'}
                fields['finish']={'const':'recipe_materials'}
                params={p['name']:{'type':p['type'],'minimum':p['minimum'],'maximum':p['maximum']}
                    for p in recipe['parameters']}
                fields['recipe_parameters']=dict(type='object',additionalProperties=False,
                    required=list(params),properties=params)
                fields['placement']=dict(type='object',additionalProperties=False,
                    required=['relation','parent_id','part','anchor','elevation_m'],properties=dict(
                    relation={'const':'floor'},parent_id={'type':'null'},part={'type':'null'},
                    anchor={'const':'centre'},elevation_m={'type':'null'}))
            else:
                from twinpulse_core.model_library import library_models
                selected_manifest=next((m for m in library_models() if m['model_id']==selected),None)
                if selected_manifest:
                    fields['variant']={'enum':selected_manifest['variants']}
                    fields['finish']={'enum':selected_manifest['finishes']}
                if 'recipe_parameters' in fields:fields['recipe_parameters']={'type':'null'}
        slots[identity] = {'type': 'object', 'additionalProperties': False,
                          'required': list(fields), 'properties': fields}
    return {'type': 'object', 'additionalProperties': False,
            'required': list(slots), 'properties': slots}


def scene_draft(structure):
    return {'schema_version': SEMANTIC_REVISION, 'summary': structure['summary'],
        'room': deepcopy(structure['room']), 'inventory': deepcopy(structure['inventory']),
        'objects': {}, 'state': 'DRAFT_INCOMPLETE', 'physical_authority': False}


def checked_batch(value, draft, identities):
    if not isinstance(value, dict) or set(value) != set(identities):
        raise SceneContractError(report([issue('SEMANTIC_BATCH_IDS_INVALID', '$.objects')]))
    problems = _shape_issues(value, batch_schema(draft['inventory'], identities,
        recipes=draft.get('model_recipes'),selections=draft.get('model_selections')), '$.objects')
    if problems:
        raise SceneContractError(report(problems))
    result = deepcopy(draft)
    for identity in identities:
        result['objects'][identity] = deepcopy(value[identity])
    return result


def revision(draft):
    # Completion flags/summary and dictionary order are not semantic changes.
    value={'room':draft['room'], 'objects':draft['objects'],
        'inventory':sorted(draft['inventory'],key=lambda row:row['id'])}
    if draft.get('model_recipes'):value['model_recipes']=draft['model_recipes']
    return canonical_sha256(value)


def compiler_diagnosis(error, draft, request):
    """Preserve typed errors; never silently send an empty compiler diagnosis."""
    if getattr(error,'contract_report',None):
        return deepcopy(error.contract_report)
    from twinpulse_core.geometry_diagnostics import geometry_issue, geometry_report
    detail=str(error);code=detail.split(':')[0]
    known=code.startswith(('PHOTO_', 'FURNITURE_', 'ROOM_ITEM_'))
    targets=[i for i in draft['objects'] if re.search(r'(?<![A-Za-z0-9_-])(?:obj_)?'+re.escape(i)+r'(?![A-Za-z0-9_-])',detail)]
    packing=getattr(error,'packing_report',None)
    if packing:
        targets=list(dict.fromkeys(targets+packing.get('remaining_ids',[])))
    room_error=code in {'PHOTO_LAYOUT_DIMENSIONS_INVALID','PHOTO_LAYOUT_USER_DIMENSIONS_CHANGED',
        'PHOTO_LAYOUT_ROOM_INVALID','PHOTO_LAYOUT_AMBIGUOUS_DIMENSIONS','PHOTO_LAYOUT_UNQUALIFIED_DIMENSIONS'}
    known=known and bool(targets or room_error)
    identities=targets or [None]
    diagnostics=geometry_report([geometry_issue(code if known else 'UNMAPPED_COMPILER_ERROR',i,
        path='$.objects.'+i if i else '$.room' if room_error else '$',
        actual=deepcopy(draft['objects'].get(i)) if i else deepcopy(draft['room']) if room_error else None,
        expected={'compiler_detail':detail,'packing':packing,
            'explicit_room_size_m':__import__('twinpulse_provider.photo_layout',fromlist=['requested_size']).requested_size(request.prompt)},
        related_ids=targets+['$room'],repairable=known) for i in identities])
    diagnostics['original_error']=detail
    return diagnostics


def geometry_repair_context(draft, diagnosis):
    """Dependency closure is per revision, never a lifetime object lock."""
    objects=draft['objects'];reasons={}
    def include(identity,reason):
        if identity in objects:reasons.setdefault(identity,set()).add(reason)
    for row in diagnosis.get('issues',[]):
        for identity in row.get('target_ids',[])+row.get('missing_ids',[])+row.get('invalid_ids',[]):
            include(identity,'diagnostic_target')
        for identity in row.get('related_ids',[]):include(identity,'diagnostic_dependency')
    def expand():
        changed=True
        while changed:
            before=set(reasons)
            for identity,value in objects.items():
                parent=value.get('placement',{}).get('parent_id')
                if identity in reasons:include(parent,'support_parent')
                if parent in reasons:include(identity,'dependent_child')
            parents={objects[i].get('placement',{}).get('parent_id') for i in reasons}-{None}
            for identity,value in objects.items():
                if value.get('placement',{}).get('parent_id') in parents:include(identity,'shared_support')
            changed=set(reasons)!=before
    if not reasons:
        for identity in objects:include(identity,'layout_replanning')
    expand();hard_ids=set(reasons)
    # Low-confidence contradictions are NOT hard failures or acceptance proof.
    # During an already-needed current-frame repair, permit their dependency
    # assemblies as exploratory candidates instead of silently starving layout
    # behind pending props. Recompute targets from the bound assessments rather
    # than trusting model-written target IDs or a stale hypothesis list.
    if (diagnosis.get('status')=='needs_revision' and diagnosis.get('issues')
            and diagnosis.get('candidate_revision')==revision(draft)
            and diagnosis.get('render_comparison')=='reviewed'
            and isinstance(diagnosis.get('frame_key'),str)
            and re.fullmatch('[a-f0-9]{64}',diagnosis['frame_key'])
            and diagnosis.get('plan_sha256')==diagnosis.get('capture',{}).get('plan_sha256')
            and diagnosis.get('capture',{}).get('candidate_revision')==revision(draft)
            and diagnosis['frame_key']==canonical_sha256(diagnosis['capture'])):
        for identity,value in diagnosis.get('assessments',{}).items():
            layout=value.get('layout',{})
            confidence=layout.get('confidence')
            if (layout.get('status')=='contradiction' and type(confidence) in (float,int)
                    and 0<confidence<.8):include(identity,'unconfirmed_current_layout_hypothesis')
    expand()
    return {'revision':'geometry-repair-context-1.1','base_revision':revision(draft),
        'hypothesis_only_ids':sorted(set(reasons)-hard_ids),
        'hypothesis_fields':['region','yaw_deg','placement'],
        'targets':[{ 'id':i,'reasons':sorted(reasons[i]),
            'source':deepcopy(next(row['source'] for row in draft['inventory'] if row['id']==i))}
            for i in sorted(reasons)],
        'room_change':'estimated_dimensions_only; explicit dimensions are protected by compiler',
        'room_change_requires_recheck':sorted(objects),
        'other_objects':'preserve by default; layout changes must improve the full validated candidate'}


def layout_for(draft):
    rows=[]
    for row in draft['inventory']:
        value=deepcopy(draft['objects'][row['id']])
        if value['model_id'].startswith('local.'):
            recipe=draft.get('model_recipes',{}).get(value['model_id'])
            if recipe is None:raise SceneContractError(report([issue('MODEL_RECIPE_SNAPSHOT_MISSING','$.objects.'+row['id'])]))
            value['model_recipe_snapshot']=deepcopy(recipe)
        elif value.get('recipe_parameters') is None:
            value.pop('recipe_parameters',None)
        rows.append(dict(id=row['id'],kind=row['kind'],source=deepcopy(row['source']),**value))
    return {'layout_version': GROUNDING_REVISION, 'summary': draft['summary'],
        'room': deepcopy(draft['room']), 'objects':rows}


def review_candidate_quality(draft, payload, provenance, observation, request):
    """Reuse current observer evidence without claiming rendered fidelity.

    Relative ordering is checkable; supports, occlusion and scale still require
    image/render review. A compiler-valid floor placement is not visual proof.
    """
    from .scene_contract import review_photo_relations
    if not request.images:
        return dict(schema_version='candidate-quality-review-1.0',status='not_applicable',
            candidate_revision=revision(draft),plan_sha256=canonical_sha256(payload),
            comparison_source='user_request_and_current_render',issues=[],render_comparison='not_run',physical_authority=False)
    relation_report=review_photo_relations(payload,observation,provenance.get('coordinate_frame'))
    by_observation={ref:row['id'] for row in draft['inventory'] for ref in row['source']['observation_ids']}
    issues=[]
    deferred={row['id'] for row in provenance.get('progressive_twin',{}).get('unresolved',[])}
    deferred_relations=[]
    for row in relation_report['issues']:
        identities=sorted({by_observation[ref] for key in ('observed_id','subject_id','object_id')
            if (ref:=row.get(key)) in by_observation})
        if set(identities)&deferred:
            # The host intentionally did not materialize these objects. Keep
            # the contradiction; do not repair a missing render as if present.
            deferred_relations.append(deepcopy(row))
            continue
        from twinpulse_core.geometry_diagnostics import geometry_issue
        objects={i:deepcopy(draft['objects'][i]) for i in identities}
        parents=sorted({v['placement']['parent_id'] for v in objects.values()
            if v.get('placement',{}).get('parent_id') in draft['objects']})
        quality_issue=geometry_issue(row['code'],identities[0] if identities else None,
            actual={'observation_relation':deepcopy(row),'semantic_objects':objects,
                'support_parents':{i:deepcopy(draft['objects'][i]) for i in parents}},
            expected={'source':'current_observation_estimate','metric_accuracy':'unverified',
                'photo_view_bounds_m':deepcopy(row.get('expected_photo_view_bounds_m')),
                'position_control':('support_parent_and_attachment_anchor' if parents else 'floor_region'),
                'repair_note':('Compare the compiled position, not only the declared region. '
                    'An attached item inherits its parent position; revise parent/anchor together '
                    'within the host-approved dependency scope and recompile all constraints.')},
            related_ids=sorted(set(identities[1:]+parents)),repairable=bool(identities))
        if type(row.get('violation_m')) in (int,float):quality_issue['violation_m']=row['violation_m']
        issues.append(quality_issue)
    return dict(schema_version='candidate-quality-review-1.0',status='needs_revision' if issues else 'uncertain',
        candidate_revision=revision(draft),plan_sha256=canonical_sha256(payload),
        issues=issues,observed_photo_relations=relation_report,
        layout_dependency_ids={identity:sorted({by_observation[other]
            for row in observation.relations if row['relation'] in
                {'left_of','right_of','in_front_of','behind','near','parallel_to','perpendicular_to','aligned_with'}
            for ref,other in ((row['subject_id'],row['object_id']),(row['object_id'],row['subject_id']))
            if by_observation.get(ref)==identity and other in by_observation
            and by_observation[other] not in deferred and by_observation[other]!=identity})
            for identity in draft['objects'] if identity not in deferred},
        **({'deferred_relations':deferred_relations,'visual_completeness':'needs_refinement'} if deferred else {}),
        support_relations='unverified_against_photo',metric_scale='estimated_not_measured',
        render_comparison='not_run',physical_authority=False)


def compile_scene(draft, observation, request, *, progressive=False):
    from twinpulse_core.geometry_checks import GeometryChecks
    from twinpulse_core.model_library import LIBRARY_VERSION
    checks=GeometryChecks(revision(draft),COMPILER_REVISION,LIBRARY_VERSION,list(draft['objects']))
    checks.mark('input_contract','running')
    try:
        payload,provenance=_compile_scene(draft,observation,request,checks,progressive=progressive)
        # The partial phase executed and diagnosed these retained children;
        # an empty issue_refs would make newly exposed support errors look like
        # regressions from an earlier blocked phase.
        pending=provenance.get('progressive_twin',{}).get('unresolved',[])
        if pending:
            support=next(r for r in checks.rows if r['check_id']=='support_packing')
            support['issue_refs']=[r['evidence']['issue_id'] for r in pending]
        return payload,{**provenance,**checks.report()}
    except Exception as error:
        diagnosis=compiler_diagnosis(error,draft,request)
        diagnosis.update(checks.failure(diagnosis))
        error.contract_report=diagnosis
        raise


def _compile_scene(draft, observation, request, checks, *, progressive=False):
    missing = [row['id'] for row in draft['inventory'] if row['id'] not in draft['objects']]
    if missing:
        raise SceneContractError(report([issue('SEMANTIC_DRAFT_INCOMPLETE', '$.objects', missing_ids=missing)],
                                        ['compile', 'Build', 'Run']))
    if draft['inventory']:
        payload, provenance = compile_layout(layout_for(draft), observation, request, None,
            check_observer=checks.mark,progressive=progressive)
    else:
        # A text-only empty room is valid. Photos still undergo coverage checks.
        checked_structure({k: deepcopy(draft[k]) for k in ('summary', 'room', 'inventory')}, request, observation)
        checks.mark('input_contract','passed')
        # These phases have no targets in an explicitly empty-room candidate.
        for phase in ('model_relations','floor_packing','support_packing','attachment_placement'):
            checks.mark(phase,'running');checks.mark(phase,'passed')
        room = draft['room']
        payload = {'plan_version': '2.2', 'scene_id': 'estimated_room', 'summary': draft['summary'],
            'image_observations': ('Photo observation has no object inventory; geometry estimated, not measured.'
                if request.images else 'Text-only estimated room; no image evidence.'), 'calls': [{'call_id': 'floor', 'tool': 'create_floor',
                'arguments': {'id': 'floor', 'center_m': [0, 0], 'size_m': [room['width_m'], room['length_m']]}}],
            'call_evidence': [{'call_id': 'floor', 'basis': 'inferred', 'observation_ids': [],
                               'note': 'Estimated room, not measured'}]}
        checks.mark('tool_executor','running')
        execute_site_tool_plan(SiteToolPlan.from_dict(payload), source='manual', source_ref=revision(draft))
        checks.mark('tool_executor','passed')
        checks.mark('placement_validation','running');checks.mark('placement_validation','passed')
        provenance = {'physical_authority': False}
    checks.mark('evidence_binding','running')
    calls = [row['call_id'] for row in payload['calls']]
    refs = [row['call_id'] for row in payload['call_evidence']]
    if set(calls) != set(refs) or len(calls) != len(set(calls)) or len(refs) != len(set(refs)):
        raise InvalidProviderResponseError('SEMANTIC_COMPILER_EVIDENCE_MISMATCH')
    checks.mark('evidence_binding','passed')
    from .semantic_bindings import BINDING_REVISION
    hypotheses = [row['id'] for row in draft['inventory']
        if row['source']['basis'] == 'inferred' and not row['source']['observation_ids']]
    return payload, {**provenance, 'semantic_revision': revision(draft), 'binding_revision': BINDING_REVISION,
        'hypotheses': hypotheses, 'hypotheses_status': 'unobserved_estimates' if hypotheses else 'none',
        'semantic_compiler': COMPILER_REVISION, 'state': 'APPROXIMATE_TWIN_READY',
        'size_status': 'explicit_user_dimensions' if __import__(
            'twinpulse_provider.photo_layout', fromlist=['requested_size']).requested_size(request.prompt)
            else 'estimated_not_measured', 'physical_authority': False}


def patch_schema(draft, observation=None, *, request=None, repair_diagnosis=None):
    # Named semantic operations only, no executable tools or arbitrary JSON paths.
    properties = batch_schema(draft['inventory'], [row['id'] for row in draft['inventory']],
        recipes=draft.get('model_recipes'),selections={i:v['model_id'] for i,v in draft['objects'].items()})['properties']
    alternatives = [{'type': 'object', 'additionalProperties': False,
        'required': ['op', 'id', 'value'], 'properties': {'op': {'const': 'update'},
            'id': {'const': identity}, 'value': schema}} for identity, schema in properties.items()]
    from .nebius_pipeline import ObservationArtifact
    observation = observation or ObservationArtifact.from_mapping({'schema_version': '1.0',
        'summary': 'No image', 'entities': [], 'relations': [], 'dimensions': [], 'ambiguities': []})
    # One generic shape, not a copy of the library for every kind. The full
    # compiler independently checks kind/model/dimensions compatibility.
    value = {'region': {'type': 'string', 'enum': list(REGIONS)},
             'yaw_deg': {'type': 'number', 'enum': [0, 90, -90, 180]},
             **_model_fields(allowed_parents={row['id']: row['kind'] for row in draft['inventory']})}
    alternatives.append({'type': 'object', 'additionalProperties': False,
        'required': ['op', 'id', 'kind', 'source', 'value'], 'properties': {
            'op': {'const': 'add'}, 'id': {'type': 'string', 'pattern': ID.pattern},
            'kind': {'type': 'string', 'enum': [k for k in KINDS if k not in ('rack','pallet_stack')]}, 'source': source_schema(observation),
            'value': {'type': 'object', 'additionalProperties': False, 'required': list(value), 'properties': value}}})
    from twinpulse_core.warehouse_models import WAREHOUSE_KINDS
    for kind in WAREHOUSE_KINDS:
        fields={'region':{'type':'string','enum':list(REGIONS)},'yaw_deg':{'type':'number','enum':[0]},
            **_model_fields(kind)}
        alternatives.append(dict(type='object',additionalProperties=False,required=['op','id','kind','source','value'],
            properties=dict(op={'const':'add'},id={'type':'string','pattern':ID.pattern},kind={'const':kind},
                source=source_schema(observation),value=dict(type='object',additionalProperties=False,
                    required=list(fields),properties=fields))))
    if request is not None:
        from .semantic_bindings import binding_fields
        for alternative in alternatives:
            if alternative['properties']['op'].get('const') != 'add':continue
            properties_add = alternative['properties']
            properties_add.pop('source')
            properties_add['evidence_ref'] = binding_fields(request, observation)['evidence_ref']
            alternative['required'] = ['op', 'id', 'kind', 'evidence_ref', 'value']
    hypotheses = [row['id'] for row in draft['inventory']
        if row['source']['basis'] == 'inferred' and not row['source']['observation_ids']]
    if hypotheses:
        alternatives.append({'type': 'object', 'additionalProperties': False,
            'required': ['op', 'id', 'reason_code'], 'properties': {'op': {'const': 'remove'},
            'id': {'type': 'string', 'enum': hypotheses}, 'reason_code': {'const': 'hypothesis'}}})
    for identity in properties:
        others = [row['id'] for row in draft['inventory'] if row['id'] != identity]
        if others:
            alternatives.append({'type': 'object', 'additionalProperties': False,
                'required': ['op', 'id', 'reason_code', 'duplicate_of'], 'properties': {
                    'op': {'const': 'remove'}, 'id': {'const': identity},
                    'reason_code': {'const': 'duplicate'}, 'duplicate_of': {'type': 'string', 'enum': others}}})
    alternatives.append({'type': 'object', 'additionalProperties': False,
        'required': ['op', 'value'], 'properties': {'op': {'const': 'room'},
            'value': layout_schema('')['properties']['room']}})
    if repair_diagnosis is not None:
        from .repair_scope import scope_operations
        alternatives.extend(scope_operations(draft, repair_diagnosis))
    return {'type': 'object', 'additionalProperties': False,
        'required': ['patch_version', 'base_revision', 'operations'], 'properties': {
        'patch_version': {'const': PATCH_REVISION}, 'base_revision': {'const': revision(draft)},
        'operations': {'type': 'array', 'minItems': 1, 'maxItems': max(33,2*len(properties)+1), 'items': {'anyOf': alternatives}}}}


def patch_candidate(draft, patch, observation, request=None, *, repair_diagnosis=None):
    """Stage a typed copy. Unique obstacles cannot be erased to fix packing.

    Removing a true observed duplicate requires another retained row grounded
    to exactly the same observation identities. Explicit saved-scene deletion
    remains in the existing reviewed change-set/Undo product workflow.
    """
    problems = _shape_issues(patch, patch_schema(draft, observation, request=request,
        repair_diagnosis=repair_diagnosis))
    if problems:
        raise SceneContractError(report(problems))
    if repair_diagnosis is not None:
        from .repair_scope import checked_scope
        checked_scope(draft, patch, repair_diagnosis)
    result = deepcopy(draft)
    touched = set()
    for operation in patch['operations']:
        if operation['op'] == 'request_scope':
            continue  # Host-approved metadata, not a geometry operation.
        identity = operation.get('id', '$room')
        if identity in touched:
            raise SceneContractError(report([issue('SEMANTIC_PATCH_DUPLICATE_TARGET', identity)]))
        touched.add(identity)
        if operation['op'] == 'room':
            result['room'] = deepcopy(operation['value'])
        elif operation['op'] == 'update':
            result['objects'][identity] = deepcopy(operation['value'])
        elif operation['op'] == 'add':
            if identity in result['objects'] or any(row['id'] == identity for row in result['inventory']):
                raise SceneContractError(report([issue('SEMANTIC_ADD_ID_EXISTS', identity)]))
            if request is not None:
                from .semantic_bindings import bind_inventory
                row = bind_inventory([{k: operation[k] for k in ('id', 'kind', 'evidence_ref')}], request, observation)[0]
                refs = set(row['source']['observation_ids'])
                if refs and any(refs.intersection(other['source']['observation_ids']) for other in result['inventory']):
                    raise SceneContractError(report([issue('SEMANTIC_ADD_OBSERVATION_ALREADY_BOUND', identity)]))
            else:
                row = {k: deepcopy(operation[k]) for k in ('id', 'kind', 'source')}
            result['inventory'].append(row)
            result['objects'][identity] = deepcopy(operation['value'])
        elif operation['op'] == 'remove':
            original = next(row for row in draft['inventory'] if row['id'] == identity)
            source = original['source']
            if operation['reason_code'] == 'hypothesis':
                result['inventory'] = [row for row in result['inventory'] if row['id'] != identity]
                result['objects'].pop(identity, None)
                continue
            other = next(row for row in draft['inventory'] if row['id'] == operation['duplicate_of'])
            if (original['kind'] != other['kind'] or not source['observation_ids']
                    or source['basis'] not in ('visual', 'inferred') or other['source'] != source
                    or other['id'] not in result['objects']):
                raise SceneContractError(report([issue('SEMANTIC_REMOVAL_NOT_PROVEN_DUPLICATE', identity)]))
            result['inventory'] = [row for row in result['inventory'] if row['id'] != identity]
            result['objects'].pop(identity, None)
    checked_payload_bytes(result, SEMANTIC_PAYLOAD_BYTES, 'SEMANTIC_PAYLOAD_BUDGET_REACHED')
    if revision(result)==revision(draft):
        raise SceneContractError(report([issue('SEMANTIC_PATCH_NO_CHANGE','$.operations',
            target_ids=sorted(touched),actual={'revision':revision(draft)},
            expected={'meaningful_geometry_or_inventory_change':True})]))
    return result


def apply_patch_candidate(draft, patch, observation, request):
    result = patch_candidate(draft, patch, observation, request=request)
    # Recompile all parents/children and collision checks in the copy. Failure
    # returns no committed candidate and cannot alter a previously valid scene.
    payload, provenance = compile_scene(result, observation, request)
    return result, payload, {**provenance, 'patch_before': revision(draft), 'patch_after': revision(result)}
