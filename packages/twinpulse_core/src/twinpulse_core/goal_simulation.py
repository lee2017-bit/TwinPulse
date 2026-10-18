# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Lossless REAL-candidate route projection into a SIM-only Burger plan.

No new route is planned here. A display receipt never grants robot authority.
"""
from copy import deepcopy
import math
from .revisions import canonical_sha256
from .site_simulation import geometry, xy


def make_goal_simulation(scene, review, assets):
    if (type(review) is not dict or review.get('schema') not in {'current-goal-preview-1.0','current-goal-preview-2.0'}
            or review.get('mode')!='REAL_CANDIDATE' or review.get('physical_authority') is not False
            or review.get('scene_revision')!=scene.revision
            or review.get('plan_id')!=canonical_sha256({k:v for k,v in review.items() if k!='plan_id'})):
        raise ValueError('GOAL_SIM_REVIEW_CHANGED')
    start=xy(review['start']);goal=xy(review['goal']);route=review['route'];yaw=review['yaw_rad']
    if (type(route) is not list or not 1<=len(route)<=64 or list(xy(route[-1]))!=list(goal)
            or type(yaw) not in (float,int) or not math.isfinite(yaw) or abs(yaw)>math.pi):
        raise ValueError('GOAL_SIM_ROUTE_INVALID')
    bounds,_,_,floor_top=geometry(scene)
    for point in (start,goal,*route):
        x,y=xy(point)
        if not (bounds[0]<=x<=bounds[1] and bounds[2]<=y<=bounds[3]):raise ValueError('GOAL_SIM_ROUTE_OUTSIDE_ROOM')
    if (type(assets) is not dict or not 1<=len(assets)<=32 or any(
            not isinstance(k,str) or k.startswith('/') or '..' in k.split('/')
            or not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v)
            for k,v in assets.items())):raise ValueError('SIM_ASSET_INVENTORY_INVALID')
    body={'schema_version':'site-goal-demonstration-1.0','mode':'SIM','scene_revision':scene.revision,
        'asset_id':'turtlebot3_burger','asset_files':deepcopy(assets),'start':list(start),'goal':list(goal),
        'yaw_rad':float(yaw),'spawn_z_m':floor_top+.002,'route':deepcopy(route),
        'max_linear_mps':.15,'max_angular_rps':.6,'tolerance_m':.04,'max_sim_time_s':120.,
        'physical_authority':False,'review':deepcopy(review)}
    return {**body,'plan_id':canonical_sha256(body)}


def checked_goal_simulation(scene,value):
    if type(value) is not dict:raise ValueError('GOAL_SIM_PLAN_INVALID')
    expected=make_goal_simulation(scene,value.get('review'),value.get('asset_files'))
    if value!=expected:raise ValueError('GOAL_SIM_PLAN_CHANGED')
    return expected
