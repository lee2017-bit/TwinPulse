# SPDX-License-Identifier: Apache-2.0
"""Bounded estimated-Twin route contract. No transport or movement authority.

The operator anchor and LiDAR relative pose are estimates, not a surveyed map.
The robot-local owner must still admit every output through its existing guard.
"""
from copy import deepcopy
import math


def pose3(value):
    return isinstance(value,(list,tuple)) and len(value)==3 and all(type(n) in (int,float) and math.isfinite(n) and abs(n)<=1000 for n in value)


def transform_pose(pose,origin,world):
    if not all(pose3(v) for v in (pose,origin,world)):raise ValueError('NAVIGATION_ANCHOR_INVALID')
    yaw=world[2]-origin[2];c,s=math.cos(yaw),math.sin(yaw);x,y=pose[0]-origin[0],pose[1]-origin[1]
    return [world[0]+c*x-s*y,world[1]+s*x+c*y,world[2]+pose[2]-origin[2]]


def route_from_plan(plan,anchor,tracking,context_id,visual_epoch):
    if not isinstance(tracking,dict) or tracking.get('status')!='ESTIMATED' or not pose3(tracking.get('pose')):
        raise ValueError('NAVIGATION_CURRENT_LIDAR_TRACKING_REQUIRED')
    origin,world=anchor['origin'],anchor['world']
    points=[transform_pose([*p,0.],world,origin)[:2] for p in plan['waypoints']]
    route=dict(schema='estimated-twin-route-1.0',waypoints=points,tracking_epoch=tracking['epoch'],
        start_pose=list(tracking['pose']),sample_s=tracking['sample_s'],context_id=context_id,
        visual_epoch=visual_epoch,target_id=plan['target_id'],target_kind=plan['target_kind'],
        target_label=plan['target_label'],anchor_world=list(world),anchor_tracking=list(origin),goal_world=list(plan['goal_xy']),
        accuracy='OPERATOR_ANCHOR_AND_RELATIVE_LIDAR_UNQUALIFIED')
    return checked_route(route,tracking,tracking['sample_s'])


def checked_route(value,tracking,now,*,tracking_age_s=.6):
    keys={'schema','waypoints','tracking_epoch','start_pose','sample_s','context_id','visual_epoch',
          'target_id','target_kind','target_label','accuracy','anchor_world','anchor_tracking','goal_world'}
    if (not isinstance(value,dict) or set(value)!=keys or value['schema']!='estimated-twin-route-1.0'
            or value['accuracy']!='OPERATOR_ANCHOR_AND_RELATIVE_LIDAR_UNQUALIFIED'
            or not pose3(value['start_pose']) or not isinstance(value['waypoints'],list)
            or not 1<=len(value['waypoints'])<=16):raise ValueError('NAVIGATION_ROUTE_SHAPE')
    if any(not isinstance(value[k],str) or not 1<=len(value[k])<=160 for k in keys-{'schema','waypoints','start_pose','sample_s','anchor_world','anchor_tracking','goal_world'}):
        raise ValueError('NAVIGATION_ROUTE_IDENTITY')
    if (not pose3(value['anchor_world']) or not pose3(value['anchor_tracking'])
            or not isinstance(value['goal_world'],list) or len(value['goal_world'])!=2 or not pose3([*value['goal_world'],0.])):
        raise ValueError('NAVIGATION_ANCHOR_INVALID')
    if any(not isinstance(p,list) or len(p)!=2 or not pose3([*p,0.]) for p in value['waypoints']):raise ValueError('NAVIGATION_ROUTE_POINTS')
    if type(value['sample_s']) not in (int,float) or not math.isfinite(value['sample_s']) or not 0<=now-value['sample_s']<=tracking_age_s:
        raise ValueError('NAVIGATION_ROUTE_SOURCE_STALE')
    current=checked_tracking(tracking,value['tracking_epoch'],now,tracking_age_s=tracking_age_s)
    if math.dist(current[:2],value['start_pose'][:2])>.05 or abs(math.remainder(current[2]-value['start_pose'][2],math.tau))>.10:
        raise ValueError('NAVIGATION_ROUTE_START_CHANGED')
    length=sum(math.dist(a,b) for a,b in zip([value['start_pose'][:2],*value['waypoints']],value['waypoints']))
    if length>5.:raise ValueError('NAVIGATION_ROUTE_LENGTH_BOUND')
    return deepcopy(value)


def checked_tracking(tracking,epoch,now,*,tracking_age_s=.6):
    if (not isinstance(tracking,dict) or tracking.get('status')!='ESTIMATED' or tracking.get('epoch')!=epoch
            or not pose3(tracking.get('pose')) or type(tracking.get('sample_s')) not in (int,float)
            or not math.isfinite(tracking['sample_s']) or not 0<=now-tracking['sample_s']<=tracking_age_s):
        raise ValueError('NAVIGATION_TRACKING_STALE_OR_CHANGED')
    return list(tracking['pose'])


def route_step(route,tracking,index,now,*,tracking_age_s=.6):
    pose=checked_tracking(tracking,route['tracking_epoch'],now,tracking_age_s=tracking_age_s);points=route['waypoints']
    while index<len(points) and math.dist(pose[:2],points[index])<=.04:index+=1
    remaining=sum(math.dist(a,b) for a,b in zip([pose[:2],*points[index:]],points[index:]))
    if index==len(points):return None,index,remaining
    p=points[index];error=math.remainder(math.atan2(p[1]-pose[1],p[0]-pose[0])-pose[2],math.tau)
    return ('left' if error>0 else 'right') if abs(error)>.06 else 'forward',index,remaining
