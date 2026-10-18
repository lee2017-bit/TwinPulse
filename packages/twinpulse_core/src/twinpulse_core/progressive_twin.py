# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Hash-bound partial inventory, never a render, task pass or motion permit."""
from copy import deepcopy
import math

from .revisions import canonical_sha256

VERSION = 'progressive-twin-1.0'
POLICY = 'progressive-acceptance-1.0'
DEPENDENCY_VERSION = 'progressive-twin-1.2'
DEPENDENCY_POLICY = 'progressive-acceptance-1.1'
AXES = {'draft_ready': 'compiled_pending_runtime', 'sim_task_pass': 'not_run',
        'real_task_ready': 'not_run', 'visual_review': 'unmeasured_needs_review'}


def issue_impact(bounds, *, hazard, robot_top_m=None, clearance_m=.05):
    """SIM-only vertical exclusion with explicit host context; unknown blocks.

    Bounds are scene estimates, not sensor evidence. Names do not affect this
    decision. No inferred decoration flag authorizes an omitted floor hazard.
    """
    if (hazard not in {'rigid', 'unknown', 'entanglement'} or
            not isinstance(bounds, (list, tuple)) or len(bounds) != 2 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in bounds) or
            not 0 <= bounds[0] <= bounds[1] <= 8):
        raise ValueError('PROGRESSIVE_IMPACT_INVALID')
    if robot_top_m is None:
        return 'task_context_required'
    if (type(robot_top_m) not in (int, float) or not math.isfinite(robot_top_m) or
            not 0 < robot_top_m <= 4 or type(clearance_m) not in (int, float) or
            not math.isfinite(clearance_m) or not 0 <= clearance_m <= 1):
        raise ValueError('PROGRESSIVE_ROBOT_ENVELOPE_INVALID')
    return ('outside_sim_envelope' if hazard == 'rigid' and
            bounds[0] > robot_top_m + clearance_m else 'task_blocked')


def envelope(plan, inventory, unresolved, source_sha256):
    materialized = {c['arguments']['id'] for c in plan['calls']}
    dependency_pending=any(r['parent_id'] not in materialized for r in unresolved)
    unresolved=deepcopy(unresolved)
    if dependency_pending:
        pending={r['id']:r for r in unresolved}
        for row in unresolved:
            if row['parent_id'] not in materialized:
                row.update(pending_ancestry(row['id'],pending,materialized))
    rows = [dict(id=r['id'], kind=r['kind'], parameters=deepcopy(r),
                 status='render_pending' if r['id'] in materialized else 'deferred') for r in inventory]
    body = dict(schema_version=DEPENDENCY_VERSION if dependency_pending else VERSION,
                policy_version=DEPENDENCY_POLICY if dependency_pending else POLICY,
                source_sha256=source_sha256, plan_sha256=canonical_sha256(plan),
                inventory=rows, unresolved=unresolved,
                axes={**AXES, 'visual_review': 'needs_refinement' if unresolved else AXES['visual_review']},
                physical_authority=False)
    return {**body, 'sha256': canonical_sha256(body)}


def checked_envelope(value, plan):
    from .scene_resources import check_scene_payload
    check_scene_payload(value)
    fields = {'schema_version', 'policy_version', 'source_sha256', 'plan_sha256',
              'inventory', 'unresolved', 'axes', 'physical_authority', 'sha256'}
    nested=isinstance(value,dict) and value.get('schema_version')==DEPENDENCY_VERSION
    if (not isinstance(value, dict) or set(value) != fields or value['schema_version'] != (DEPENDENCY_VERSION if nested else VERSION) or
            value['policy_version'] != (DEPENDENCY_POLICY if nested else POLICY) or value['physical_authority'] is not False or
            value['plan_sha256'] != canonical_sha256(plan) or
            value['sha256'] != canonical_sha256({k: v for k, v in value.items() if k != 'sha256'}) or
            not isinstance(value['inventory'], list) or not value['inventory'] or
            not isinstance(value['unresolved'], list) or not isinstance(value['axes'], dict) or
            value['axes'] != {**AXES, 'visual_review': 'needs_refinement' if value['unresolved'] else AXES['visual_review']} or
            not isinstance(value['source_sha256'], str) or len(value['source_sha256']) != 64 or
            any(c not in '0123456789abcdef' for c in value['source_sha256'])):
        raise ValueError('PROGRESSIVE_ENVELOPE_INVALID')
    materialized = {c['arguments']['id'] for c in plan['calls']}
    ids, deferred = set(), set()
    for row in value['inventory']:
        if (not isinstance(row, dict) or set(row) != {'id', 'kind', 'parameters', 'status'} or
                not isinstance(row['id'], str) or row['id'] in ids or
                not isinstance(row['parameters'], dict) or row['parameters'].get('id') != row['id'] or
                row['parameters'].get('kind') != row['kind'] or
                row['status'] != ('render_pending' if row['id'] in materialized else 'deferred')):
            raise ValueError('PROGRESSIVE_INVENTORY_INVALID')
        ids.add(row['id'])
        if row['status'] == 'deferred': deferred.add(row['id'])
    model_ids = {c['arguments']['id'] for c in plan['calls'] if c['tool'] not in {'create_floor', 'create_wall'}}
    if not model_ids <= ids:
        raise ValueError('PROGRESSIVE_INVENTORY_COVERAGE_INVALID')
    issues = set()
    parameters={row['id']:row['parameters'] for row in value['inventory']}
    parents={c['arguments']['id']:c['arguments'] for c in plan['calls']}
    for row in value['unresolved']:
        dependency=nested and isinstance(row,dict) and row.get('parent_id') in deferred
        row_fields={'id','parent_id','part','code','reason','status','hazard','bounds_z_m',
            'impact','uncertainty','source','evidence'}
        if dependency:row_fields|={'materialized_anchor_id','root_issue_id','ancestor_path'}
        if (not isinstance(row, dict) or set(row) != row_fields or
                row['id'] not in deferred or row['id'] in issues or
                row['parent_id'] not in (materialized | deferred if nested else materialized) or
                row['status'] != 'deferred' or row['impact'] != 'task_context_required' or
                not isinstance(row['source'], dict) or not isinstance(row['evidence'], dict)):
            raise ValueError('PROGRESSIVE_UNRESOLVED_INVALID')
        issue_impact(row['bounds_z_m'], hazard=row['hazard'])
        if row['parent_id'] in materialized:
            if (row['uncertainty']!='estimated_support_not_world_verified' or
                    row['code']!='PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE' or row['reason'] not in
                    {'SURFACE_CAPACITY_EXCEEDED','SUPPORT_CLEARANCE_EXCEEDED'}):
                raise ValueError('PROGRESSIVE_UNRESOLVED_INVALID')
            _check_pending_geometry(row,parameters[row['id']],parents[row['parent_id']])
        else:
            if (not nested or row['uncertainty']!='pending_support_ancestor_not_world_verified' or
                    row['code']!='PARENT_VALIDATION_PENDING' or row['reason']!='PARENT_VALIDATION_PENDING'):
                raise ValueError('PROGRESSIVE_UNRESOLVED_INVALID')
            hazard,bounds=pending_dependency_geometry(parameters[row['id']],parameters[row['parent_id']])
            if (row['part']!=parameters[row['id']]['placement']['part'] or row['hazard']!=hazard or
                    row['bounds_z_m']!=bounds or row['source'].get('basis') not in ('visual','user','inferred') or
                    row['source'].get('observation_ids')!=parameters[row['id']]['observation_ids'] or
                    row['evidence'].get('target_ids')!=[row['id']] or
                    row['parent_id'] not in row['evidence'].get('related_ids',[]) or
                    row['evidence'].get('actual',{}).get('reason')!='PARENT_VALIDATION_PENDING'):
                raise ValueError('PROGRESSIVE_PENDING_DEPENDENCY_INVALID')
        issues.add(row['id'])
    if issues != deferred:
        raise ValueError('PROGRESSIVE_DEFERRED_COVERAGE_INVALID')
    # Every deferred chain must terminate at a checked materialized support.
    # Do not flatten it or invent a world pose for the unplaced parent.
    pending={r['id']:r for r in value['unresolved']}
    for identity in pending if nested else ():
        pending_root(identity,pending,materialized)
        if pending[identity]['parent_id'] in deferred and any(pending[identity].get(k)!=v
                for k,v in pending_ancestry(identity,pending,materialized).items()):
            raise ValueError('PROGRESSIVE_PENDING_DEPENDENCY_INVALID')
    if nested and not any(r['parent_id'] in deferred for r in pending.values()):
        raise ValueError('PROGRESSIVE_PENDING_DEPENDENCY_INVALID')
    if nested and any(parameters[i].get('placement',{}).get('parent_id') in deferred
            for i in ids-deferred):
        raise ValueError('PROGRESSIVE_PENDING_CHILD_MATERIALIZED')
    return deepcopy(value)


def pending_root(identity,pending,materialized):
    return pending_ancestry(identity,pending,materialized)['materialized_anchor_id']


def pending_ancestry(identity,pending,materialized):
    seen=set()
    path=[]
    while identity not in materialized:
        if identity in seen or identity not in pending:
            raise ValueError('PROGRESSIVE_PENDING_DEPENDENCY_INVALID')
        seen.add(identity);path.append(identity);identity=pending[identity]['parent_id']
    if not path:raise ValueError('PROGRESSIVE_PENDING_DEPENDENCY_INVALID')
    return dict(materialized_anchor_id=identity,ancestor_path=path+[identity],
        root_issue_id=pending[path[-1]]['evidence']['issue_id'])


def pending_dependency_geometry(parameters,parent_parameters):
    """Native supported descendant with unknown world pose: retain full risk.

    A temporary local probe validates the named catalogue support only. Its
    coordinates are never published; bounds cover the entire allowed height.
    The separately checked parent chain must reach a materialized root.
    """
    from .room_item_catalog import room_item_catalog_version
    parent_kind=parent_parameters.get('kind')
    if (parent_kind not in {'box','tabletop_item','surface_covering'} or
            not pending_support_eligible(parent_parameters) or
            parameters.get('placement',{}).get('parent_id')!=parent_parameters.get('id')):
        raise ValueError('PROGRESSIVE_PENDING_DEPENDENCY_INVALID')
    size=parent_parameters['dimensions_m']
    parent=dict(id=parent_parameters['id'],kind=parent_kind,label=parent_kind,
        catalog_version=room_item_catalog_version(parent_kind),position_m=[0.,0.,size[2]/2],
        dimensions_m=size,yaw_deg=parent_parameters['yaw_deg'],observation_time_utc=None)
    from .room_items import expand_room_item
    expand_room_item(parent)
    hazard,_=pending_support_geometry(parameters,parent,parameters['placement']['part'])
    return hazard,[0.,8.]


def _check_pending_geometry(issue, parameters, parent):
    """Recheck retained risk/vertical bounds from the saved catalogue geometry.

    A checksummed record is not a signature. Changing its bounds or labelling an
    unknown/floor prop rigid must not make a corrupt record admissible.
    """
    try:
        placement=parameters['placement']
        hazard,bounds=pending_support_geometry(parameters,parent,issue['part'])
        valid=(placement['relation']=='surface' and placement['parent_id']==issue['parent_id'] and
            placement['part']==issue['part'] and issue['hazard']==hazard and
            all(abs(actual-expected)<1e-6 for actual,expected in zip(issue['bounds_z_m'],bounds)) and
            # Match the persisted photo-layout source contract, not a new enum.
            issue['source'].get('basis') in ('visual','user','inferred') and
            issue['source'].get('observation_ids')==parameters['observation_ids'])
    except (ValueError,KeyError,TypeError,IndexError,AttributeError) as error:
        raise ValueError('PROGRESSIVE_PENDING_GEOMETRY_INVALID') from error
    if not valid:raise ValueError('PROGRESSIVE_PENDING_GEOMETRY_INVALID')


def pending_support_eligible(parameters):
    from .room_item_catalog import ROOM_ITEM_KINDS
    return (parameters.get('kind') in ROOM_ITEM_KINDS and parameters['kind'] not in
        {'office_chair','floor_fan','clothes_rack','door_leaf','pallet'} and
        parameters.get('placement',{}).get('relation')=='surface')


def pending_support_geometry(parameters,parent,part):
    """Draft-only retained native support child; never an omitted safe obstacle.

    Keep the original catalogue hazard and all expanded vertical keepouts. The
    unresolved item's world XY/support is still unknown, so task gates remain
    responsible for rejecting its use, even when the materialized subset fits.
    """
    from .photo_quality import support_surface
    from .room_items import room_item_risk,expand_room_item
    placement=parameters['placement']
    if (not pending_support_eligible(parameters) or
            placement['parent_id']!=parent['id'] or placement['part']!=part):
        raise ValueError('PROGRESSIVE_PENDING_GEOMETRY_INVALID')
    from .model_library import library_models
    model=next(row for row in library_models() if row['kind']==parameters['kind'])
    if (parameters['model_id']!=model['model_id'] or parameters['variant'] not in model['variants'] or
            parameters['finish'] not in model['finishes'] or placement['anchor']!='centre' or
            placement['elevation_m'] is not None):
        raise ValueError('PROGRESSIVE_PENDING_GEOMETRY_INVALID')
    surface=support_surface(parent,part)
    if surface is None:raise ValueError('PROGRESSIVE_PENDING_GEOMETRY_INVALID')
    top=surface.transform.position_m[2]+surface.shape.dimensions_m[2]/2
    from .room_item_catalog import room_item_catalog_version
    probe=dict(id=parameters['id'],kind=parameters['kind'],label=parameters['kind'],
        catalog_version=room_item_catalog_version(parameters['kind']),position_m=[0,0,top+parameters['dimensions_m'][2]/2],
        dimensions_m=parameters['dimensions_m'],yaw_deg=parameters['yaw_deg'],observation_time_utc=None)
    risk=room_item_risk(probe)
    hazard=risk if risk in {'entanglement','unknown'} else 'rigid'
    # Include the nominal envelope as well as actual catalogue parts. Existing
    # elevated visual-only records retain their identical legacy bounds.
    parts=expand_room_item(probe)
    bounds=[min([top]+[p.transform.position_m[2]-p.shape.dimensions_m[2]/2 for p in parts]),
        max([top+parameters['dimensions_m'][2]]+[p.transform.position_m[2]+p.shape.dimensions_m[2]/2 for p in parts])]
    issue_impact(bounds,hazard=hazard)
    return hazard,bounds


def summary(value, *, current_plan_sha256):
    """Small public payload retaining pending state across reload and edits."""
    if value is None: return None
    return dict(schema_version=value['schema_version'], policy_version=value['policy_version'],
        plan_sha256=value['plan_sha256'], current=current_plan_sha256 == value['plan_sha256'],
        axes=deepcopy(value['axes']), inventory_count=len(value['inventory']),
        materialized_count=sum(r['status'] == 'render_pending' for r in value['inventory']),
        unresolved=[{k: deepcopy(r[k]) for k in ('id', 'parent_id', 'code', 'reason', 'status', 'impact','hazard','bounds_z_m')}
                    for r in value['unresolved']], physical_authority=False)


def require_task_context(value, *, robot_top_m=None, physical=False):
    if value is None or not value['unresolved']: return
    if value.get('policy_version')==DEPENDENCY_POLICY:
        raise ValueError('PROGRESSIVE_TASK_UNRESOLVED: '+', '.join(r['id'] for r in value['unresolved']))
    blocked = [r['id'] for r in value['unresolved'] if physical or
               issue_impact(r['bounds_z_m'], hazard=r['hazard'], robot_top_m=robot_top_m) != 'outside_sim_envelope']
    if blocked:
        raise ValueError('PROGRESSIVE_TASK_UNRESOLVED: ' + ', '.join(blocked))
