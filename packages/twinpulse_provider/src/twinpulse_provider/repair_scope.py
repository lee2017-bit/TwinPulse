# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Host-checked request-local geometry scope; never saved-scene edit authority.

Scope requests and their atomic patch share one response/paid attempt. A free
text justification cannot unlock arbitrary objects. Existing input/evidence,
dimension and geometry validators still run after application.
"""
from copy import deepcopy

SCOPE_REVISION = 'geometry-scope-1.1'
DELTA_REVISION = 'semantic-delta-1.0'


def delta_schema(draft, diagnosis):
    """Expose only this conflict's permitted edits, not model-written scope rows."""
    from .semantic_scene import batch_schema, revision
    context,options=scope_options(draft,diagnosis)
    allowed={row['id'] for row in context['targets']}|{row['id'] for row in options}
    selections={i:v['model_id'] for i,v in draft['objects'].items()}
    slots=batch_schema(draft['inventory'],sorted(allowed),recipes=draft.get('model_recipes'),selections=selections)['properties']
    for identity in context.get('hypothesis_only_ids',[]):
        slots[identity]['properties']={k:v for k,v in slots[identity]['properties'].items()
            if k in context['hypothesis_fields']}
    changes={identity:{'anyOf':[{'type':'null'},dict(type='object',additionalProperties=False,
        properties=slot['properties'])]} for identity,slot in slots.items()}
    from .photo_layout import layout_schema
    return dict(type='object',additionalProperties=False,required=['patch_version','base_revision','changes','room'],properties={
        'patch_version':{'const':DELTA_REVISION},'base_revision':{'const':revision(draft)},
        'changes':dict(type='object',additionalProperties=False,required=list(changes),properties=changes),
        'room':{'anyOf':[{'type':'null'},layout_schema('')['properties']['room']]}})


def normalize_delta(draft, value, diagnosis):
    """Derive exact changed updates and existing scope evidence; no extra authority."""
    from .semantic_scene import _shape_issues,PATCH_REVISION
    from .scene_contract import SceneContractError,report,issue
    problems=_shape_issues(value,delta_schema(draft,diagnosis))
    if problems:raise SceneContractError(report(problems))
    context,options=scope_options(draft,diagnosis)
    targets={row['id'] for row in context['targets']};eligible={}
    for option in options:eligible.setdefault(option['id'],option)
    operations=[]
    if value['room'] is not None and value['room']!=draft['room']:
        operations.append(dict(op='room',value=deepcopy(value['room'])))
    for identity,changes in value['changes'].items():
        if changes is None:continue
        after=deepcopy(draft['objects'][identity]);after.update(deepcopy(changes))
        if after==draft['objects'][identity]:continue
        if identity not in targets:
            option=eligible.get(identity)
            if option is None:raise SceneContractError(report([issue('SEMANTIC_PATCH_OUTSIDE_REPAIR_SCOPE','$.changes.'+identity)]))
            operations.append(dict(op='request_scope',id=identity,anchor_id=option['anchor_id'],reason_code=option['reason_code']))
        operations.append(dict(op='update',id=identity,value=after))
    if not operations:raise SceneContractError(report([issue('SEMANTIC_PATCH_NO_CHANGE','$.changes')]))
    return dict(patch_version=PATCH_REVISION,base_revision=value['base_revision'],operations=operations)


def scope_options(draft, diagnosis):
    from .semantic_scene import geometry_repair_context
    from .photo_layout import _model_fields
    context = geometry_repair_context(draft, diagnosis)
    allowed = {row['id'] for row in context['targets']}
    objects = draft['objects']
    kinds = {row['id']: row['kind'] for row in draft['inventory']}
    issues = diagnosis.get('issues', [])
    codes = {row.get('code') for row in issues}
    packing = bool(codes & {'PHOTO_LAYOUT_REGION_FULL', 'PHOTO_LAYOUT_OVERLAP',
        'PHOTO_PLACEMENT_OVERLAP', 'FURNITURE_OVERLAP'})
    # Collision-derived evidence stays an explicit atomic scope request. Never
    # put a placed blocker in diagnostic related_ids to unlock it implicitly.
    blockers={};blocker_children={}
    for issue in issues:
        actual=issue.get('actual')
        expected=issue.get('expected')
        packing_value=(actual.get('packing') if isinstance(actual,dict) else None) or (
            expected.get('packing') if isinstance(expected,dict) else None)
        if not isinstance(packing_value,dict):continue
        proof=packing_value.get('conflict_set',{})
        if not isinstance(proof,dict):continue
        if proof.get('schema_version')!='photo-packing-conflict-set-1.0' or proof.get('physical_authority') is not False:continue
        for conflict in proof.get('conflicts',[])[:32]:
            if not isinstance(conflict,dict):continue
            anchor=conflict.get('id')
            if anchor not in allowed:continue
            blockers[anchor]={row['id'] for row in conflict.get('placed_blockers',[])[:32]
                if isinstance(row,dict) and row.get('id') in objects and
                type(row.get('blocked_candidate_count')) is int and row['blocked_candidate_count']>0}
            for row in conflict.get('placed_blockers',[])[:32]:
                if not isinstance(row,dict) or row.get('id') not in blockers[anchor]:continue
                for child in row.get('dependency_ids',[]):
                    if child in objects and objects[child].get('placement',{}).get('parent_id')==row['id']:
                        blocker_children.setdefault(anchor,set()).add(child)
    rows = []
    # An unconfirmed visual hypothesis must not unlock third-party packing
    # neighbours (and their unrestricted model/dimension fields).
    for anchor in sorted(allowed-set(context.get('hypothesis_only_ids',[]))):
        value = objects[anchor]
        placement = value['placement']
        schema = _model_fields(kinds[anchor], allowed_parents=kinds,recipes=draft.get('model_recipes'),
            parent_models=draft.get('model_selections'))['placement']
        parent_choices = {parent for branch in schema.get('anyOf', [])
            for parent in branch.get('properties', {}).get('parent_id', {}).get('enum', [])}
        for identity in sorted(set(objects)-allowed):
            other = objects[identity]
            if identity in blocker_children.get(anchor,set()):
                rows.append(dict(id=identity,anchor_id=anchor,reason_code='packing_neighbor',
                    evidence='compiled_blocker_attachment_expands_occupied_proxy'))
            if other['placement']['relation'] != 'floor':
                continue
            if packing and placement['relation'] == 'floor':
                # Image-relative regions are estimates. This eligibility only
                # connects neighbouring packing cells; it is not free-space proof.
                a, b = value['region'].split('_'), other['region'].split('_')
                vertical = ('front', 'middle', 'rear'); horizontal = ('left', 'centre', 'right')
                if identity in blockers.get(anchor,set()) or (abs(vertical.index(a[0])-vertical.index(b[0])) <= 1 and
                        abs(horizontal.index(a[1])-horizontal.index(b[1])) <= 1):
                    rows.append(dict(id=identity, anchor_id=anchor, reason_code='packing_neighbor',
                        evidence='compiled_occupied_proxy_blocks_candidate_grid' if identity in blockers.get(anchor,set()) else
                            'same_or_adjacent_estimated_packing_region'))
            if (placement['relation'] in ('surface', 'drape') and identity in parent_choices
                    and any(anchor in row.get('target_ids', []) for row in issues)):
                rows.append(dict(id=identity, anchor_id=anchor, reason_code='support_alternative',
                    evidence='library_supported_parent_of_diagnosed_child'))
    return context, rows


def scope_operations(draft, diagnosis):
    _, options = scope_options(draft, diagnosis)
    return [{'type': 'object', 'additionalProperties': False,
        'required': ['op', 'id', 'anchor_id', 'reason_code'], 'properties': {
            'op': {'const': 'request_scope'}, 'id': {'const': row['id']},
            'anchor_id': {'const': row['anchor_id']}, 'reason_code': {'const': row['reason_code']}}}
        for row in options]


def checked_scope(draft, patch, diagnosis):
    from .semantic_scene import revision, geometry_repair_context
    from .scene_contract import SceneContractError, report, issue
    context, options = scope_options(draft, diagnosis)
    identities = {row['id'] for row in context['targets']}
    proof = {(row['id'], row['anchor_id'], row['reason_code']): row for row in options}
    requests = [row for row in patch['operations'] if row['op'] == 'request_scope']
    accepted = []
    seen = set()
    for row in requests:
        if not any(op.get('id')==row['id'] and (op['op']=='remove' or
                op['op']=='update' and op['value']!=draft['objects'][row['id']]) for op in patch['operations']):
            raise SceneContractError(report([issue('SEMANTIC_SCOPE_REQUIRES_CHANGED_UPDATE', '$.operations',
                target_ids=[row['id']],detail='request_scope must accompany an actual changed update/remove for this ID.')]))
        key = (row['id'], row['anchor_id'], row['reason_code'])
        if row['id'] in seen or key not in proof:
            raise SceneContractError(report([issue('SEMANTIC_SCOPE_REQUEST_REJECTED', '$.operations',
                target_ids=[row['id']], related_ids=[row['anchor_id']])]))
        seen.add(row['id'])
        accepted.append(deepcopy(proof[key]))
    # Expand only actual dependency closure (children/shared support), never
    # room-wide identities based on the model's explanation text.
    if accepted:
        expanded = geometry_repair_context(draft, {'issues': [
            {'target_ids': sorted(identities | seen)}]})
        identities.update(row['id'] for row in expanded['targets'])
    for row in patch['operations']:
        changes = row['op']=='remove' or (row['op']=='update' and
            row['value'] != draft['objects'][row['id']])
        if changes and row['id'] not in identities:
            raise SceneContractError(report([issue('SEMANTIC_PATCH_OUTSIDE_REPAIR_SCOPE', '$.operations',
                target_ids=[row['id']], expected={'allowed_ids': sorted(identities)})]))
        if changes and row['id'] in context.get('hypothesis_only_ids',[]):
            if (row['op']!='update' or any(row['value'].get(k)!=v for k,v in draft['objects'][row['id']].items()
                    if k not in context['hypothesis_fields'])):
                raise SceneContractError(report([issue('SEMANTIC_HYPOTHESIS_GEOMETRY_CHANGE_REJECTED',
                    '$.operations',target_ids=[row['id']],expected={'fields':context['hypothesis_fields']})]))
    return dict(schema_version=SCOPE_REVISION, base_revision=revision(draft),
        requested=deepcopy(requests), accepted=accepted, allowed_ids=sorted(identities),
        physical_authority=False)
