# SPDX-License-Identifier: Apache-2.0
"""Plan once from an operator-declared start pose on the Twin model.

The start pose is declared, not localized; the plan is model geometry, not a
sensor map, and grants no motion authority. Each compiled step is an ordinary
finite command that keeps every robot-side guard and admission check.
"""
import math
from .bounded_grid_plan import NoBoundedPath
from .robot_survey import observation_candidates, route_to, route_length, task_clearance

SCOPE='DECLARED_START_MODEL_PLAN_NOT_LOCALIZED'
MAX_LEG_M=1.0      # 1 m finite forward completed on the physical robot (2026-10-25)
MIN_TURN_RAD=.02
MIN_LEG_M=.01
# Declared start + odometry accumulate heading error and the scan omits small
# furniture: physical routes keep a wider berth (more conservative only).
PHYSICAL_ROUTE_CLEARANCE_M=.35


def _wrap(a):return math.atan2(math.sin(a),math.cos(a))


def _reachable(start,geometry,observed_cells,clearance):
    """Observation stops reachable from the start, with their path length (one A* each)."""
    free=None if observed_cells is None else {(math.floor(c[0]/.1),math.floor(c[1]/.1)) for c in observed_cells if c[2]=='free'}
    reachable={}
    heading=(math.cos(start[2]),math.sin(start[2]))
    for p in observation_candidates(geometry):
        if free is not None and (math.floor(p[0]/.1),math.floor(p[1]/.1)) not in free:continue
        # Survey the space the robot faces (the declared heading), not every
        # open-plan area behind it.
        if (p[0]-start[0])*heading[0]+(p[1]-start[1])*heading[1]<0:continue
        try:length=route_length(start,route_to(start,p,geometry,observed_cells=observed_cells,clearance_m=clearance))
        except NoBoundedPath:continue
        # Same open space as the start: the path is nearly straight. Stops behind
        # doorways (other rooms, unscanned clutter) are excluded from a room survey.
        if length<=1.2*math.dist(start[:2],p)+.2:reachable[tuple(p)]=length
    return reachable


def _spread_step(pose,visited,reachable,geometry,observed_cells,remaining,clearance,min_spacing_m):
    """Farthest reachable stop from every visited point that still leaves the return budget.

    Nearest-first (robot_survey.next_observation) circles the start; survey stops
    should spread out so they sample different parts of the room.
    """
    def spread(p):return min(math.dist(p,q[:2]) for q in visited)
    candidates=sorted((p for p in reachable if spread(p)>=min_spacing_m),key=lambda p:(-spread(p),p))
    for goal in candidates[:12]:
        if math.dist(pose[:2],goal)+reachable[goal]+.25>remaining:continue  # cheap lower bound
        try:route=route_to(pose,list(goal),geometry,observed_cells=observed_cells,clearance_m=clearance)
        except NoBoundedPath:continue
        if route_length(pose,route)+reachable[goal]+.25<=remaining:return route,list(goal)
    return None,None


def plan_survey(start,geometry,observed_cells=None,*,kind='physical',budget_m=6.,max_waypoints=4,min_spacing_m=.6):
    """Bounded, spread-out observation stops on the model, then back to the declared start."""
    clearance=max(task_clearance(kind,planning=True),PHYSICAL_ROUTE_CLEARANCE_M if kind=='physical' else 0.)
    reachable=_reachable(start,geometry,observed_cells,clearance)
    pose=list(start);visited=[list(start)];polyline=[];waypoints=[];remaining=budget_m;reason=None
    while len(waypoints)<max_waypoints:
        route,goal=_spread_step(pose,visited,reachable,geometry,observed_cells,remaining,clearance,min_spacing_m)
        if route is None:reason='NO_REACHABLE_STOP_WITH_RETURN_BUDGET';break
        remaining-=route_length(pose,route)
        polyline+=route;waypoints.append(list(goal))
        last=route[-2] if len(route)>1 else pose
        pose=[*goal,math.atan2(goal[1]-last[1],goal[0]-last[0])]
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
