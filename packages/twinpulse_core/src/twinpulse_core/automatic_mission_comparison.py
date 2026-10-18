# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Evaluate two executed synthetic missions; never infer physical collisions."""
import math
from .revisions import canonical_sha256


def checked_conditions(value):
    keys={'schema','project_id','room_revision','world_revision','start','goal','seed','dynamics',
          'geometry_revision','duration_s','footprint_radius_m','collision_penalty','revision'}
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('COMPARISON_CONDITIONS_SHAPE')
    if (value['schema']!='automatic-mission-conditions-1.0' or type(value['seed']) is not int or value['seed']!=0
            or value['dynamics']!='static_kinematic_raycast_v1' or value['duration_s']!=45.
            or type(value['collision_penalty']) is not int or value['collision_penalty']!=100 or value['footprint_radius_m']!=.18):
        raise ValueError('COMPARISON_POLICY_CHANGED')
    for key,size in (('start',3),('goal',2)):
        if type(value[key]) is not list or len(value[key])!=size or any(
                type(v) not in (int,float) or not math.isfinite(v) or abs(v)>12 for v in value[key]):
            raise ValueError('COMPARISON_COORDINATES')
    if canonical_sha256({k:v for k,v in value.items() if k!='revision'})!=value['revision']:
        raise ValueError('COMPARISON_CONDITIONS_HASH')
    return value


def compare_automatic_missions(conditions,arms):
    checked_conditions(conditions)
    if set(arms)!={'baseline','corrected'}:raise ValueError('COMPARISON_TWO_ARMS_REQUIRED')
    for key,policy in (('baseline','align_only'),('corrected','correct_walls')):
        arm=arms[key]
        if (arm['conditions_revision']!=conditions['revision'] or arm['policy']!=policy
                or arm['physical_validation']!='NOT_RUN' or arm['provenance']!='synthetic_raycast'):
            raise ValueError('COMPARISON_CONDITIONS_OR_PROVENANCE_CHANGED')
        for metric in ('distance_m','source_elapsed_s','goal_error_m'):
            if type(arm[metric]) not in (int,float) or not math.isfinite(arm[metric]) or arm[metric]<0:
                raise ValueError('COMPARISON_METRIC_INVALID')
        if type(arm['collision_episodes']) is not int or arm['collision_episodes']<0:
            raise ValueError('COMPARISON_COLLISIONS_INVALID')
    rows={k:{**v,'collision_penalty_points':v['collision_episodes']*conditions['collision_penalty'],
               'arrival_reward':100 if v['state']=='MISSION_ARRIVED' else 0,
               'score':(100 if v['state']=='MISSION_ARRIVED' else 0)-v['collision_episodes']*conditions['collision_penalty']}
          for k,v in arms.items()}
    comparable=all(v['state']=='MISSION_ARRIVED' and not v.get('cleanup_error') for v in arms.values())
    before,after=rows['baseline'],rows['corrected']
    body={'schema':'automatic-mission-comparison-1.0','conditions':conditions,'arms':rows,
          'scope':'OUTPUT_REACTIVE_SYNTHETIC_NOT_ROBOT','comparable_arrivals':comparable,
          'distance_reduction_m':before['distance_m']-after['distance_m'] if comparable else None,
          'source_time_reduction_s':before['source_elapsed_s']-after['source_elapsed_s'] if comparable else None,
          'collision_episode_reduction':before['collision_episodes']-after['collision_episodes'],
          'score_change':after['score']-before['score'],'physical_validation':'NOT_RUN',
          'motion_authorized':False,'physical_demo_ready':False,
          'limitations':['Synthetic truth is not measured room geometry or a robot trajectory.',
                         'Static kinematic dynamics; no friction, braking, Wi-Fi or physical collision proof.',
                         'PC fit/runtime duration is reported separately from source-clock travel time.',
                         'No improvement is promised; failed or stopped arms are not comparable arrivals.']}
    return {**body,'revision':canonical_sha256(body)}
