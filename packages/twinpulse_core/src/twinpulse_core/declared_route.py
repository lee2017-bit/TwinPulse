# SPDX-License-Identifier: Apache-2.0
"""Plan once from an operator-declared start pose on the Twin model.

The start pose is declared, not localized; the plan is model geometry, not a
sensor map, and grants no motion authority. Each compiled step is an ordinary
finite command that keeps every robot-side guard and admission check.
"""
import math
from .bounded_grid_plan import NoBoundedPath
from .robot_survey import next_observation, route_to, route_length, task_clearance

SCOPE='DECLARED_START_MODEL_PLAN_NOT_LOCALIZED'
MAX_LEG_M=1.0      # 1 m finite forward completed on the physical robot (2026-10-25)
MIN_TURN_RAD=.02
MIN_LEG_M=.01


def _wrap(a):return math.atan2(math.sin(a),math.cos(a))


def plan_survey(start,geometry,observed_cells=None,*,kind='physical',budget_m=6.,max_waypoints=4):
    """Bounded observation stops on the model, then back to the declared start."""
    clearance=task_clearance(kind,planning=True)
    pose=list(start);visited=[list(start)];polyline=[];waypoints=[];remaining=budget_m;reason=None
    while len(waypoints)<max_waypoints:
        step=next_observation(pose,start,visited,geometry,remaining,return_required=True,
            observed_cells=observed_cells,clearance_m=clearance)
        if step['route'] is None:reason=step['reason'];break
        remaining-=route_length(pose,step['route'])
        polyline+=step['route'];waypoints.append(list(step['goal']))
        last=step['route'][-2] if len(step['route'])>1 else pose
        pose=[*step['goal'],math.atan2(step['goal'][1]-last[1],step['goal'][0]-last[0])]
        visited.append(pose)
    else:reason='WAYPOINT_LIMIT'
    if not waypoints:raise ValueError('DECLARED_ROUTE_NO_REACHABLE_WAYPOINT:'+str(reason))
    returning=route_to(pose,start[:2],geometry,observed_cells=observed_cells,clearance_m=clearance)
    polyline+=returning
    return dict(start=list(start),waypoints=waypoints,polyline=[list(p) for p in polyline],
        length_m=route_length(start,polyline),stop_reason=reason,scope=SCOPE,clearance_m=clearance)


def compile_moves(start,polyline,*,final_yaw=None,max_leg_m=MAX_LEG_M):
    """Turn-then-drive steps whose integration reproduces the polyline."""
    x,y,yaw=start;steps=[]
    def turn(target):
        nonlocal yaw
        delta=_wrap(target-yaw)
        if abs(delta)>=MIN_TURN_RAD:
            steps.append(dict(direction='left' if delta>0 else 'right',amount=abs(delta)))
        yaw=target
    for gx,gy in polyline:
        distance=math.hypot(gx-x,gy-y)
        if distance<MIN_LEG_M:continue
        turn(math.atan2(gy-y,gx-x))
        legs=math.ceil(distance/max_leg_m)
        for _ in range(legs):steps.append(dict(direction='forward',amount=distance/legs))
        x,y=gx,gy
    if final_yaw is not None:turn(final_yaw)
    return steps


def move_text(step):
    """Exact text accepted by the existing finite-command parser."""
    if step['direction']=='forward':return 'forward %.1fcm'%(step['amount']*100)
    return '%s %.2f degrees'%(step['direction'],math.degrees(step['amount']))


def integrate(start,steps):
    x,y,yaw=start
    for s in steps:
        if s['direction']=='forward':x+=s['amount']*math.cos(yaw);y+=s['amount']*math.sin(yaw)
        else:yaw=_wrap(yaw+(s['amount'] if s['direction']=='left' else -s['amount']))
    return [x,y,yaw]


__all__=['SCOPE','plan_survey','compile_moves','move_text','integrate','NoBoundedPath']
