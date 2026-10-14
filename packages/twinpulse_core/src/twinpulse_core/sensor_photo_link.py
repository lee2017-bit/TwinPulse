# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit saved endpoint / authored wall correspondences, never calibration.

Proper SE(2) only: no scale/reflection, furniture inference, TF or motion grant.
Held-out validation points are not used to estimate the candidate transform.
"""
import math
from .native_registration import _area, MIN_TRIANGLE_AREA_M2, MAX_RESIDUAL_M
from .room_localization import compose, inverse, scene_outline


def photo_wall_anchors(objects, scan_height_m):
    outline=scene_outline(objects,scan_height_m)
    floor=next(o for o in objects if o['kind']=='floor');anchors=[]
    for obj in objects:
        if obj['kind']!='wall':continue
        p,d=obj['transform']['position_m'],obj['shape']['dimensions_m']
        if not p[2]-d[2]/2<=scan_height_m<=p[2]+d[2]/2:continue
        walls=scene_outline([floor,obj],scan_height_m)
        for i,segment in enumerate(walls['segments']):
            anchors.append({'id':obj['id']+':'+str(i),'object_id':obj['id'],'corner':i,'xy_m':segment[0],
                            'basis':'AUTHORED_PHOTO_WALL_CORNER_NOT_MEASURED'})
    return {'anchors':anchors,'outline':outline,'reference_kind':'PHOTO_APPROXIMATION_NOT_METRIC_REFERENCE'}


def link_sensor_to_photo(sensor, context, pairs):
    if sensor['status']!='SENSOR_MAP_GEOMETRIC_CANDIDATE':raise ValueError('SENSOR_POSITION_NOT_UNIQUE')
    if type(pairs) is not list or not 4<=len(pairs)<=16:raise ValueError('LINK_REQUIRES_3_FIT_AND_1_VALIDATION_PAIRS')
    endpoints=sensor['reference_endpoint_cells'];anchors={a['id']:a for a in context['anchors']}
    rows=[];seen=set();targets=set()
    for pair in pairs:
        if type(pair) is not dict or set(pair)!={'endpoint_index','anchor_id','role'}:raise ValueError('LINK_PAIR_SHAPE')
        index=pair['endpoint_index'];target=pair['anchor_id'];role=pair['role']
        if type(index) is not int or not 0<=index<len(endpoints):raise ValueError('LINK_ENDPOINT_NOT_RECORDED')
        if type(target) is not str or target not in anchors:raise ValueError('LINK_WALL_ANCHOR_NOT_CURRENT')
        if index in seen or target in targets:raise ValueError('LINK_DUPLICATE_CORRESPONDENCE')
        if role not in ('fit','validation'):raise ValueError('LINK_PAIR_ROLE')
        seen.add(index);targets.add(target)
        p,q=endpoints[index][:2],anchors[target]['xy_m']
        if len(p)!=2 or len(q)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>30 for v in p+q):
            raise ValueError('LINK_POINT_VALUE')
        rows.append({**pair,'reference_xy_m':list(p),'room_xy_m':list(q),
                     'endpoint_source_original_frames':endpoints[index][3:5]})
    fit=[r for r in rows if r['role']=='fit'];validation=[r for r in rows if r['role']=='validation']
    if len(fit)<3 or not validation:raise ValueError('LINK_REQUIRES_3_FIT_AND_1_VALIDATION_PAIRS')
    source=[r['reference_xy_m'] for r in fit];target=[r['room_xy_m'] for r in fit]
    if min(_area(source),_area(target))<MIN_TRIANGLE_AREA_M2:raise ValueError('LINK_FIT_POINTS_COLLINEAR_OR_TOO_SMALL')
    sx,sy=[sum(p[i] for p in source)/len(source) for i in (0,1)]
    tx,ty=[sum(p[i] for p in target)/len(target) for i in (0,1)]
    dot=sum((p[0]-sx)*(q[0]-tx)+(p[1]-sy)*(q[1]-ty) for p,q in zip(source,target))
    cross=sum((p[0]-sx)*(q[1]-ty)-(p[1]-sy)*(q[0]-tx) for p,q in zip(source,target))
    if math.hypot(dot,cross)<1e-12:raise ValueError('LINK_ROTATION_DEGENERATE')
    yaw=math.atan2(cross,dot);c,s=math.cos(yaw),math.sin(yaw)
    transform=[tx-c*sx+s*sy,ty-s*sx-c*sy,yaw]
    for row in rows:
        row['projected_room_xy_m']=compose(transform,[*row['reference_xy_m'],0])[:2]
        row['residual_m']=math.dist(row['projected_room_xy_m'],row['room_xy_m'])
    fit=[r for r in rows if r['role']=='fit'];validation=[r for r in rows if r['role']=='validation']
    rms=math.sqrt(sum(r['residual_m']**2 for r in fit)/len(fit));fit_max=max(r['residual_m'] for r in fit)
    validation_max=max(r['residual_m'] for r in validation)
    passes=max(fit_max,validation_max)<=MAX_RESIDUAL_M
    best=sensor['best_diagnostic_hypothesis']
    room_from_query=compose(transform,best['reference_from_query_odom_candidate'])
    pose=compose(transform,best['sensor_pose_reference_candidate'])
    overlays=[{**o,'points':[compose(transform,[*p,0])[:2] for p in o['points']],
               'sensor_pose_room_candidate':compose(transform,o['sensor_pose_reference_candidate'])} for o in sensor['overlays']]
    return {'schema':'sensor-photo-link-review-1.0','status':'APPROXIMATE_VISUAL_LINK_CANDIDATE' if passes else 'ANCHOR_MISMATCH',
            'pairs':rows,'fit_rms_m':rms,'fit_max_residual_m':fit_max,'validation_max_residual_m':validation_max,
            'draft_residual_threshold_m':MAX_RESIDUAL_M,'room_from_reference_candidate':transform,
            'room_from_query_odom_candidate':room_from_query,'query_from_room_candidate':inverse(room_from_query),
            'sensor_pose_room_candidate':pose if passes else None,'diagnostic_sensor_pose_room':pose,
            'overlays':overlays,'outline':context['outline'],'scale':1.,'rotation_determinant':1.,
            'reference_kind':context['reference_kind'],'correspondences_verified':False,
            'validation_basis':'OPERATOR_SELECTED_HELD_OUT_CORRESPONDENCES_NOT_INDEPENDENT_SURVEY',
            'uncertainty':'FIT_RESIDUAL_ONLY_PHYSICAL_POSE_UNCERTAINTY_UNKNOWN',
            'photo_geometry_changed':False,'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False}


def preview_link_goal(link, goal):
    if link['status']!='APPROXIMATE_VISUAL_LINK_CANDIDATE':raise ValueError('LINK_ANCHORS_NOT_CONSISTENT')
    if type(goal) is not list or len(goal)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in goal):
        raise ValueError('LINK_GOAL_FINITE_XY_REQUIRED')
    x0,x1,y0,y1=link['outline']['bounds_m']
    if not x0<=goal[0]<=x1 or not y0<=goal[1]<=y1:raise ValueError('GOAL_OUTSIDE_ROOM')
    return {'room_goal_xy_m':goal,'query_odom_goal_candidate_m':compose(link['query_from_room_candidate'],[*goal,0])[:2],
            'scope':'HISTORICAL_QUERY_ONLY_NOT_CURRENT_ROBOT','collision_clearance_verified':False,
            'motion_authorized':False,'mission_request':None}
