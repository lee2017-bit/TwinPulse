# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Compile a dependency-complete visual subset, keeping the full work intact.

This separate preview cannot satisfy the full inventory contract or authorize
navigation. The ordinary compiler still checks geometry of every shown object.
"""
from copy import deepcopy
from dataclasses import replace

from .scene_contract import role_of
from .errors import InvalidProviderResponseError
from .semantic_scene import checked_structure, checked_batch, compile_scene, revision


def room_seed_schema(request):
    from .photo_layout import layout_schema
    return dict(type='object', additionalProperties=False, required=['summary','room'], properties=dict(
        summary=dict(type='string', minLength=1, maxLength=240),
        room=layout_schema(request.prompt)['properties']['room']))


def checked_room_seed(value, observation, request):
    from .semantic_scene import _shape_issues
    from .scene_contract import SceneContractError, report
    issues=_shape_issues(value, room_seed_schema(request))
    if issues:
        raise SceneContractError(report(issues))
    # The complete observation remains in the checkpoint. This stage makes no
    # inventory/coverage claim; only the visible estimated room shell is checked.
    empty=replace(observation, entities=(), relations=(), dimensions=())
    checked_structure({**value, 'inventory': []}, request, empty)
    return deepcopy(value)


def compile_room_seed(seed, observation, request):
    from twinpulse_core import SiteToolPlan, execute_site_tool_plan, canonical_sha256
    checked_room_seed(seed, observation, request)
    w,l,h=(seed['room'][key] for key in ('width_m','length_m','height_m'))
    calls=[dict(call_id='floor', tool='create_floor', arguments=dict(id='floor', center_m=[0,0], size_m=[w,l]))]
    for name,x,y,sx,sy in (('left',-w/2,0,.08,l),('right',w/2,0,.08,l),('rear',0,l/2,w,.08)):
        calls.append(dict(call_id=name+'_wall',tool='create_wall',arguments=dict(id=name+'_wall',
            position_m=[x,y,h/2],dimensions_m=[sx,sy,h],yaw_deg=0)))
    plan=dict(plan_version='2.2', scene_id='estimated_room_preview', summary=seed['summary'],
        image_observations='Room shell estimate only; object inventory and metric accuracy are unverified.',
        calls=calls, call_evidence=[dict(call_id=row['call_id'], basis='inferred',observation_ids=[],
            note='Display-only estimated room shell; no object coverage or motion authority') for row in calls])
    execute_site_tool_plan(SiteToolPlan.from_dict(plan),source='manual',source_ref=canonical_sha256(seed))
    count=sum(1 for row in observation.entities if role_of(row) in ('object','unknown'))
    return plan, dict(schema_version='generation-preview-1.0',state='building',
        candidate_revision=canonical_sha256(seed),scene_revision=None,rendered_count=0,pending_count=count,
        inventory_count=count,preview_only=True,physical_authority=False)


def parameter_order(draft, observation):
    """Schedule targets, preserving the model's original inventory and IDs."""
    from twinpulse_core.furniture import furniture_kinds
    from twinpulse_core.warehouse_models import WAREHOUSE_KINDS
    entities={row['id']: row for row in observation.entities}
    parents={row['object_id'] for row in observation.relations if row.get('relation') in ('on','supported_by','attached_to')}
    def importance(row):
        refs=row['source']['observation_ids']
        is_parent=bool(set(refs)&parents)
        structural=row['kind'] in (*furniture_kinds(),*WAREHOUSE_KINDS,'office_chair','clothes_rack','door_leaf','wall_storage')
        area=max((entities[identity].get('confidence',0) for identity in refs if identity in entities),default=0)
        return (0 if structural else 1 if is_parent else 2, -area)
    # Stable ties keep the observer/model ordering, never a photo-specific list.
    return [row['id'] for row in sorted(draft['inventory'],key=importance)]


def compile_generation_preview(draft, observation, request):
    # Recheck the complete source inventory first. Missing observations are not
    # excused by the later, strictly display-only projection.
    checked_structure({k: draft[k] for k in ('summary', 'room', 'inventory')}, request, observation)
    inventory = {row['id']: row for row in draft['inventory']}
    pending = {}
    candidates = {}
    for identity, value in draft['objects'].items():
        try:
            checked_batch({identity: value}, {**draft, 'objects': {}}, [identity])
            candidates[identity] = value
        except (ValueError, InvalidProviderResponseError) as error:
            if not getattr(error, 'contract_report', {}).get('issues'):
                raise
            pending[identity] = dict(id=identity, reason_code='PARAMETER_VALIDATION_FAILED')
    selected = set()
    for _ in range(len(candidates)+1):
        added = set()
        for identity, value in candidates.items():
            placement = value['placement']
            if placement['relation'] in ('floor', 'wall', 'ceiling') or placement['parent_id'] in selected:
                added.add(identity)
        if added <= selected:
            break
        selected |= added
    # Only the display projection is reduced. Every source object and original
    # error remains in the full checkpoint and final compilation/repair loop.
    # A bad parent also defers its descendants; independent objects can render.
    for _ in range(len(selected)+1):
        subset = deepcopy(draft)
        subset['inventory'] = [row for row in subset['inventory'] if row['id'] in selected]
        subset['objects'] = {key: value for key, value in subset['objects'].items() if key in selected}
        refs = {ref for identity in selected for ref in inventory[identity]['source']['observation_ids']}
        entities = tuple(row for row in observation.entities if role_of(row) not in ('object', 'unknown') or row['id'] in refs)
        ids = {row['id'] for row in entities}
        projected = replace(observation, entities=entities,
            relations=tuple(row for row in observation.relations if row['subject_id'] in ids and row['object_id'] in ids),
            dimensions=tuple(row for row in observation.dimensions if row['target_id'] in ids))
        try:
            plan, provenance = compile_scene(subset, projected, request, progressive=True)
            break
        except (ValueError, InvalidProviderResponseError) as error:
            issues = getattr(error, 'contract_report', {}).get('issues', [])
            # Internal/unmapped/input failures never masquerade as valid work.
            if not issues or any(row.get('repairable') is not True for row in issues):
                raise
            excluded = {identity for row in issues for identity in row.get('target_ids', []) if identity in selected}
            if not excluded:
                raise
            for identity in excluded:
                pending[identity] = dict(id=identity, reason_code=next(
                    row['code'] for row in issues if identity in row.get('target_ids', [])))
            while True:
                descendants = {identity for identity in selected-excluded
                    if candidates[identity]['placement']['parent_id'] in excluded}
                if not descendants:
                    break
                for identity in descendants:
                    pending[identity] = dict(id=identity, reason_code='PARENT_VALIDATION_PENDING',
                        blocked_by=[candidates[identity]['placement']['parent_id']])
                excluded |= descendants
            selected -= excluded
    shown = {call['arguments'].get('id') for call in plan['calls']} & selected
    if not selected:
        # Preserve the visible walls while inventory/parent parameters are pending.
        plan,_=compile_room_seed({key:deepcopy(draft[key]) for key in ('summary','room')},observation,request)
    for row in provenance.get('progressive_twin', {}).get('unresolved', []):
        pending[row['id']] = dict(id=row['id'], reason_code=row['code'], blocked_by=[row['parent_id']])
    for identity in inventory.keys()-shown:
        if identity not in pending:
            value = draft['objects'].get(identity)
            parent = value['placement']['parent_id'] if value else None
            pending[identity] = dict(id=identity,
                reason_code='PARENT_NOT_READY' if value else 'PARAMETERS_PENDING',
                **({'blocked_by': [parent]} if parent in inventory else {}))
    summary = dict(schema_version='generation-preview-1.0', state='building',
        candidate_revision=revision(draft), scene_revision=None,
        rendered_count=len(shown), pending_count=len(inventory)-len(shown), inventory_count=len(inventory),
        pending_objects=list(pending.values()), preview_only=True, physical_authority=False)
    return plan, provenance, summary
