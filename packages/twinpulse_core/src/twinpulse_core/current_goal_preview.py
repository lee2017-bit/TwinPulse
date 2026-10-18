# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current sensor-bound candidate routes; never a lease or motion authority.

The caller supplies an existing admitted adapter's current evidence, not JSON
from a browser or a saved terminal pose. Same grid/clearance as ObservedMission.
An approval can be checked again immediately before the first nonzero output.
"""
from copy import deepcopy
import math
import re
from .bounded_grid_plan import plan_bounded_grid
from .local_navigation import finite
from .revisions import canonical_sha256
from .room_localization import compose, inverse, angle
from .simulation_goal import coordinates, goal_review
from .site_simulation import geometry


def current_binding(evidence, context, now, room_revision):
    if (type(context) is not dict or not context or type(evidence) is not dict
            or any(evidence.get(k)!=v for k,v in context.items())):
        raise ValueError('GOAL_PREVIEW_SOURCE_CONTEXT_CHANGED')
    if (not finite(now) or not finite(evidence.get('sample_s'))
            or not 0<=now-evidence['sample_s']<.2-1e-9):
        raise ValueError('GOAL_PREVIEW_CURRENT_EVIDENCE_STALE')
    if evidence.get('room_revision')!=room_revision:
        raise ValueError('GOAL_PREVIEW_ROOM_CHANGED')
    if (evidence.get('state')!='TRACKING_CANDIDATE'
            or evidence.get('alignment_status')!='ALIGNMENT_CANDIDATE'):
        raise ValueError('GOAL_PREVIEW_CURRENT_LOCALIZATION_REQUIRED')
    for key in ('map_revision','alignment_revision','room_revision'):
        if not isinstance(evidence.get(key),str) or not re.fullmatch('[a-f0-9]{64}',evidence[key]):
            raise ValueError('GOAL_PREVIEW_REVISION_INVALID')
    for key in ('pose_map','room_from_map'):
        row=evidence.get(key)
        if type(row) not in (tuple,list) or len(row)!=3 or any(not finite(v) or abs(v)>20 for v in row):
            raise ValueError('GOAL_PREVIEW_POSE_OR_TRANSFORM_INVALID')
    radius=evidence.get('footprint_radius_m',.18)
    if not finite(radius) or not 0<radius<=1:raise ValueError('GOAL_PREVIEW_FOOTPRINT_INVALID')
    # Bind the actual grid as well as its declared revision. A malformed source
    # that changes cells without changing revision cannot reuse an approval.
    cells=evidence.get('cells')
    if type(cells) is not list or len(cells)>18000:raise ValueError('GOAL_PREVIEW_GRID_INVALID')
    bounds=evidence.get('bounds');size=evidence.get('cell_size_m',.10)
    if (type(bounds) not in (tuple,list) or len(bounds)!=4 or any(not finite(v) or abs(v)>20 for v in bounds)
            or not finite(size) or size!=.10):raise ValueError('GOAL_PREVIEW_GRID_INVALID')
    return {'context':deepcopy(context),'room_revision':room_revision,
        'map_revision':evidence['map_revision'],'alignment_revision':evidence['alignment_revision'],
        'pose_map':list(evidence['pose_map']),'room_from_map':list(evidence['room_from_map']),
        'bounds':list(bounds),'cells_revision':canonical_sha256(sorted([r[:3] for r in cells])),'cell_size_m':size,
        'footprint_radius_m':max(.18,radius)}


# Candidate admission bounds, NOT measured localization accuracy. Margin is
# added, never subtracted, from the existing collision envelope. Field scope
# and qualification remain separate. V1 bytes/strict semantics are unchanged.
ROUTE_ADMISSION={'policy':'fresh-reviewed-route-envelope-1.0',
    'max_start_delta_m':.010,'max_start_yaw_delta_rad':.020,'extra_clearance_m':.010}


def review_source_matches(review,current,*,new_session=False):
    if type(review) is not dict or type(current) is not dict or set(review)!=set(current):return False
    return all(review[k]==current[k] for k in review if not (new_session and k=='session_id'))


def goal_preview(scene,text,evidence,context,now,*,furniture=None,selection=None,revalidate_route=False):
    room_revision=evidence.get('room_revision') if type(evidence) is dict else None
    binding=current_binding(evidence,context,now,room_revision)
    explicit_start,_=coordinates(text)
    if explicit_start is not None:raise ValueError('GOAL_PREVIEW_START_MUST_BE_CURRENT_SENSOR')
    start=compose(binding['room_from_map'],binding['pose_map'])
    clearance=binding['footprint_radius_m']+.05+.03*1.2+(.010 if revalidate_route else 0.)
    bounds,boxes,discs,_=geometry(scene)
    room_to_map=inverse(binding['room_from_map'])
    map_boxes=[];map_discs=[]
    for cx,cy,hx,hy,yaw in boxes:
        x,y,a=compose(room_to_map,[cx,cy,yaw]);map_boxes.append([x,y,hx,hy,a])
    for cx,cy,radius in discs:
        x,y,_=compose(room_to_map,[cx,cy,0.]);map_discs.append([x,y,radius])
    def plan(point):
        if math.dist(start[:2],point)<.10:raise ValueError('GOAL_PREVIEW_GOAL_TOO_CLOSE')
        if not (bounds[0]+clearance<=point[0]<=bounds[1]-clearance
                and bounds[2]+clearance<=point[1]<=bounds[3]-clearance):
            raise ValueError('GOAL_PREVIEW_OUTSIDE_ROOM')
        target=compose(inverse(binding['room_from_map']),[*point,0.])[:2]
        route=plan_bounded_grid(binding['pose_map'][:2],target,binding['bounds'],
            boxes=map_boxes,discs=map_discs,resolution=.10,clearance=clearance,observed_cells=evidence['cells'],cell_size_m=.10)
        body={'schema':'current-goal-preview-1.0','mode':'REAL_CANDIDATE',
            'scene_revision':scene.revision,'binding':binding,'start':list(start[:2]),'yaw_rad':start[2],
            'goal':list(point),'route':[compose(binding['room_from_map'],[*p,0.])[:2] for p in route],
            'goal_contract':{'mode':'NAVIGATE_TWIN_GOAL','xy':list(point),'room_revision':room_revision,'duration_s':45.},
            'obstacles_map':{'boxes':map_boxes,'discs':map_discs},
            'max_linear_mps':.03,'max_angular_rps':.20,'physical_authority':False}
        if revalidate_route:
            body.update(schema='current-goal-preview-2.0',admission=deepcopy(ROUTE_ADMISSION))
            # Preserve the exact requested room endpoint in the SIM review.
            # The native inverse transform still validates the whole route;
            # avoid a double-transform rounding difference at its last point.
            body['route'][-1]=list(point)
        return {**body,'plan_id':canonical_sha256(body)}
    return goal_review(scene,text,start[:2],{},yaw=start[2],furniture=furniture,selection=selection,
        planner=plan,approach_margin=max(.30,clearance+.04),
        planner_context=dict(mode='REAL_CANDIDATE', resolution_m=.10, clearance_m=clearance))


def check_preview(value,evidence,context,now,goal):
    if (type(value) is not dict or value.get('schema') not in {'current-goal-preview-1.0','current-goal-preview-2.0'}
            or value.get('mode')!='REAL_CANDIDATE' or value.get('physical_authority') is not False
            or value.get('plan_id')!=canonical_sha256({k:v for k,v in value.items() if k!='plan_id'})
            or value.get('goal_contract')!=goal):raise ValueError('GOAL_PREVIEW_PLAN_CHANGED')
    current=current_binding(evidence,context,now,goal['room_revision'])
    if value['schema']=='current-goal-preview-1.0':
        if current!=value.get('binding'):raise ValueError('GOAL_PREVIEW_START_MAP_OR_SOURCE_CHANGED')
    else:
        old=value.get('binding')
        if value.get('admission')!=ROUTE_ADMISSION or type(old) is not dict:
            raise ValueError('GOAL_PREVIEW_ADMISSION_CHANGED')
        # A fresh explicitly owned worker may have a new session ID; boot,
        # release, source, origin, project, epoch and every other key remain
        # exact. This data check grants no session/ownership permission.
        if (not review_source_matches(old.get('context'),current['context'],new_session=True)
                or any(current[k]!=old.get(k) for k in ('room_revision','alignment_revision','room_from_map',
                    'bounds','cell_size_m','footprint_radius_m'))):
            raise ValueError('GOAL_PREVIEW_START_MAP_OR_SOURCE_CHANGED')
        pose=old.get('pose_map')
        if (type(pose) is not list or len(pose)!=3 or any(not finite(v) for v in pose)
                or math.dist(pose[:2],current['pose_map'][:2])>ROUTE_ADMISSION['max_start_delta_m']
                or abs(angle(pose[2]-current['pose_map'][2]))>ROUTE_ADMISSION['max_start_yaw_delta_rad']):
            raise ValueError('GOAL_PREVIEW_START_OUTSIDE_REVIEW_ENVELOPE')
        transform=current['room_from_map'];to_map=inverse(transform)
        if (value.get('start')!=compose(old['room_from_map'],pose)[:2]
                or value.get('yaw_rad')!=compose(old['room_from_map'],pose)[2]
                or value.get('goal')!=goal['xy']
                or value.get('max_linear_mps')!=.03 or value.get('max_angular_rps')!=.20):
            raise ValueError('GOAL_PREVIEW_PLAN_CHANGED')
        route=[compose(to_map,[*p,0.])[:2] for p in value['route']]
        target=compose(to_map,[*goal['xy'],0.])[:2]
        obstacles=value['obstacles_map']
        # Recheck the complete reviewed path, not a map hash equality and not
        # just the start cell. Missing/conflicting/new occupied cells block.
        for start in (pose[:2],current['pose_map'][:2]):
            plan_bounded_grid(start,target,current['bounds'],resolution=.10,
                clearance=current['footprint_radius_m']+.05+.03*1.2+ROUTE_ADMISSION['extra_clearance_m'],
                boxes=obstacles['boxes'],discs=obstacles['discs'],observed_cells=evidence['cells'],
                cell_size_m=.10,checked_route=route)
    return deepcopy(value)
