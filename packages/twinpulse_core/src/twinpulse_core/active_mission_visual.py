# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded visual-only frame; engine/stage/project/geometry/session bound."""
from copy import deepcopy
import math
import re
from .revisions import canonical_sha256


def checked_active_frame(value):
    keys={'schema','engine_session_id','stage_epoch','project_id','objects_revision','job_id','sequence','visual','revision'}
    if not isinstance(value,dict) or set(value)!=keys or value['schema']!='active-mission-frame-1.0':raise ValueError('ACTIVE_VISUAL_SHAPE')
    for key in ('engine_session_id','stage_epoch','project_id'):
        if not isinstance(value[key],str) or not re.fullmatch('[A-Za-z0-9_.-]{1,128}',value[key]):raise ValueError('ACTIVE_VISUAL_CONTEXT')
    if not isinstance(value['job_id'],str) or not re.fullmatch('[a-f0-9]{32}',value['job_id']):raise ValueError('ACTIVE_VISUAL_SESSION')
    if type(value['sequence']) is not int or not 1<=value['sequence']<=1000:raise ValueError('ACTIVE_VISUAL_SEQUENCE')
    if not isinstance(value['objects_revision'],str) or not re.fullmatch('[a-f0-9]{64}',value['objects_revision']):raise ValueError('ACTIVE_VISUAL_ROOM')
    visual=value['visual']
    fields={'schema','session_id','context','state','room_revision','route_revision','map_revision','alignment_revision',
        'pose_room','goal_room','route_room','scan_room','trajectory_room','motion_authorized','physical_demo_ready','provenance','revision'}
    if (not isinstance(visual,dict) or set(visual)!=fields or visual['schema']!='automatic-mission-visual-1.0'
        or visual['session_id']!=value['job_id'] or visual['motion_authorized'] is not False
        or visual['physical_demo_ready'] is not False or visual['pose_room'] is None
        or visual['state'] not in {'SURVEYING','ALIGNING_PHOTO','DRIVING','REPLANNING','ARRIVED','FAILED'}
        or visual['provenance'] not in {'live_sensor','synthetic_raycast'}):raise ValueError('ACTIVE_VISUAL_SOURCE')
    context=visual['context']
    if visual['provenance']=='live_sensor':
        from .observation_stream import checked_context
        context=checked_context(context)
        if context['origin']!='live_ros' or context['source_revision']!=context['release_id']:
            raise ValueError('ACTIVE_VISUAL_CONTEXT')
    elif (not isinstance(context,dict) or set(context)!={'project_id','source_revision','epoch'}
        or type(context['epoch']) is not int or context['epoch']<1
        or not isinstance(context['source_revision'],str) or not re.fullmatch('[a-f0-9]{64}',context['source_revision'])):
        raise ValueError('ACTIVE_VISUAL_CONTEXT')
    if context['project_id']!=value['project_id']:raise ValueError('ACTIVE_VISUAL_PROJECT')
    if not isinstance(visual['room_revision'],str):raise ValueError('ACTIVE_VISUAL_ROOM')
    for key in ('room_revision','route_revision','map_revision','alignment_revision','revision'):
        row=visual[key]
        if row is not None and (not isinstance(row,str) or not re.fullmatch('[a-f0-9]{64}',row)):raise ValueError('ACTIVE_VISUAL_REVISION')
    for rows,size,limit in (([visual['pose_room']],3,1),([visual['goal_room']] if visual['goal_room'] is not None else [],2,1),
                           (visual['route_room'],2,16),(visual['scan_room'],2,160),(visual['trajectory_room'],3,512)):
        if (not isinstance(rows,list) or len(rows)>limit or any(type(p) is not list or len(p)!=size
            or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>12.1 for x in p) for p in rows)):
            raise ValueError('ACTIVE_VISUAL_GEOMETRY')
    if visual['revision']!=canonical_sha256({k:v for k,v in visual.items() if k!='revision'}):raise ValueError('ACTIVE_VISUAL_HASH')
    if value['revision']!=canonical_sha256({k:v for k,v in value.items() if k!='revision'}):raise ValueError('ACTIVE_FRAME_HASH')
    return deepcopy(value)


DISPLAY_STATUSES={'ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED','ACTIVE_VISUAL_RENDER_FAILED',
    'ACTIVE_GEOMETRY_COMPOSED_NOT_CURRENT','ACTIVE_GEOMETRY_RENDER_FAILED',
    'ACTIVE_VISUAL_OUT_OF_ORDER','ACTIVE_VISUAL_ENGINE_OR_ROOM_CHANGED','ACTIVE_VISUAL_LEASE_OR_TIMELINE',
    'ACTIVE_VISUAL_UNOWNED_ROOT','ACTIVE_VISUAL_BURGER_REQUIRED','ACTIVE_VISUAL_UNAVAILABLE',
    'ACTIVE_VISUAL_STALE','NO_ACTIVE_MISSION','CURRENT_ROOM_POSE_UNAVAILABLE','ISAAC_ROOM_GEOMETRY_CHANGED',
    'ISAAC_CONTROL_LEASE_REQUIRED','ISAAC_ROOM_RECOMPOSITION_REQUIRED','NOT_STARTED'}


def checked_display_result(value):
    if value is None:return None
    base={'job_id','sequence','status'}
    if (not isinstance(value,dict) or set(value) not in (base,base|{'error_code','error_type'})
        or not isinstance(value['job_id'],str) or not re.fullmatch('[a-f0-9]{32}',value['job_id'])
        or type(value['sequence']) is not int or not 1<=value['sequence']<=1000
        or value['status'] not in DISPLAY_STATUSES):raise ValueError('ACTIVE_DISPLAY_RESULT')
    if set(value)!=base and (value['status']!='ACTIVE_GEOMETRY_RENDER_FAILED'
            or not isinstance(value['error_code'],str) or not re.fullmatch('[A-Z0-9_]{1,120}',value['error_code'])
            or not isinstance(value['error_type'],str) or not re.fullmatch('[A-Za-z0-9_]{1,80}',value['error_type'])):
        raise ValueError('ACTIVE_DISPLAY_RESULT')
    return deepcopy(value)


def checked_active_geometry(value):
    """A bounded display-only permission, no scene/code/pose or motion authority."""
    fields={'schema','engine_session_id','stage_epoch','project_id','job_id','sequence',
            'previous_objects_revision','objects_revision','correction_revision','revision'}
    if not isinstance(value,dict) or set(value)!=fields or value['schema']!='active-mission-geometry-1.0':
        raise ValueError('ACTIVE_GEOMETRY_SHAPE')
    for key in ('engine_session_id','stage_epoch','project_id'):
        if not isinstance(value[key],str) or not re.fullmatch('[A-Za-z0-9_.-]{1,128}',value[key]):
            raise ValueError('ACTIVE_GEOMETRY_CONTEXT')
    if not isinstance(value['job_id'],str) or not re.fullmatch('[a-f0-9]{32}',value['job_id']):
        raise ValueError('ACTIVE_GEOMETRY_SESSION')
    if type(value['sequence']) is not int or not 1<=value['sequence']<=1000:raise ValueError('ACTIVE_GEOMETRY_SEQUENCE')
    for key in ('previous_objects_revision','objects_revision','correction_revision','revision'):
        if not isinstance(value[key],str) or not re.fullmatch('[a-f0-9]{64}',value[key]):raise ValueError('ACTIVE_GEOMETRY_REVISION')
    if value['previous_objects_revision']==value['objects_revision']:raise ValueError('ACTIVE_GEOMETRY_UNCHANGED')
    if canonical_sha256({k:v for k,v in value.items() if k!='revision'})!=value['revision']:
        raise ValueError('ACTIVE_GEOMETRY_HASH')
    return deepcopy(value)
