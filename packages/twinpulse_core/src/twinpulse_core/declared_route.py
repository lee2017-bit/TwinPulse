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
# Survey stops (where the robot pauses and turns) stay well inside open floor:
# the scan omits plants/leaves and odometry drifts ~2.5 deg + .3 deg/.75 m
# (2026-10-25 physical runs). Paths may still pass at the route clearance.
PHYSICAL_STOP_CLEARANCE_M=.6
ARRIVED_M=.04
HEADING_TOLERANCE_RAD=.035


def _wrap(a):return math.atan2(math.sin(a),math.cos(a))


def _key(x,y):return (math.floor(x/.1),math.floor(y/.1))


def _clear_of(p,blocked,geometry,radius):
    """No non-free cell or model obstacle within radius of p (stop placement only)."""
    k=math.ceil(radius/.1);cx,cy=_key(*p)
    for ix in range(cx-k,cx+k+1):
        for iy in range(cy-k,cy+k+1):
            if (ix,iy) in blocked and math.dist(p,((ix+.5)*.1,(iy+.5)*.1))<radius:return False
    for x0,y0,x1,y1 in geometry.get('obstacles') or []:
        if math.dist(p,(min(max(p[0],x0),x1),min(max(p[1],y0),y1)))<radius:return False
    return True


def _candidates(geometry,observed_cells):
    """Survey stop candidates: a 0.3 m lattice over free cells (finer than the
    shared 0.65 m survey grid, which left few stops inside a narrow room)."""
    if observed_cells is None:return observation_candidates(geometry)
    seen=set();out=[]
    for c in observed_cells:
        if c[2]!='free':continue
        k=(round(c[0]/.3),round(c[1]/.3))
        if k not in seen:seen.add(k);out.append([k[0]*.3,k[1]*.3])
    return sorted(out)[:2048]


def _reachable(start,geometry,observed_cells,clearance,stop_clearance=0.,max_distance_m=math.inf):
    """Observation stops reachable from the start, with their path length (one A* each)."""
    free=None if observed_cells is None else {_key(c[0],c[1]) for c in observed_cells if c[2]=='free'}
    blocked=set() if observed_cells is None else {_key(c[0],c[1]) for c in observed_cells if c[2]!='free'}
    reachable={}
    heading=(math.cos(start[2]),math.sin(start[2]))
    for p in _candidates(geometry,observed_cells):
        if free is not None and (math.floor(p[0]/.1),math.floor(p[1]/.1)) not in free:continue
        # Survey the space the robot faces (the declared heading), not every
        # open-plan area behind it.
        if (p[0]-start[0])*heading[0]+(p[1]-start[1])*heading[1]<0:continue
        if math.dist(start[:2],p)*2+.25>max_distance_m:continue  # cannot go and come back
        if stop_clearance and not _clear_of(p,blocked,geometry,stop_clearance):continue
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
    # Cheap lower bound first, so far-but-unaffordable stops do not use up the A* checks.
    candidates=sorted((p for p in reachable if spread(p)>=min_spacing_m
                       and math.dist(pose[:2],p)+reachable[p]+.25<=remaining),key=lambda p:(-spread(p),p))
    for goal in candidates[:12]:
        if math.dist(pose[:2],goal)+reachable[goal]+.25>remaining:continue  # cheap lower bound
        try:route=route_to(pose,list(goal),geometry,observed_cells=observed_cells,clearance_m=clearance)
        except NoBoundedPath:continue
        if route_length(pose,route)+reachable[goal]+.25<=remaining:return route,list(goal)
    return None,None


def plan_survey(start,geometry,observed_cells=None,*,kind='physical',budget_m=6.,max_waypoints=4,min_spacing_m=.6):
    """Bounded, spread-out observation stops on the model, then back to the declared start."""
    clearance=max(task_clearance(kind,planning=True),PHYSICAL_ROUTE_CLEARANCE_M if kind=='physical' else 0.)
    reachable=_reachable(start,geometry,observed_cells,clearance,PHYSICAL_STOP_CLEARANCE_M if kind=='physical' else 0.,budget_m)
    pose=list(start);visited=[list(start)];polyline=[];legs=[];waypoints=[];remaining=budget_m;reason=None
    while len(waypoints)<max_waypoints:
        route,goal=_spread_step(pose,visited,reachable,geometry,observed_cells,remaining,clearance,min_spacing_m)
        if route is None:reason='NO_REACHABLE_STOP_WITH_RETURN_BUDGET';break
        remaining-=route_length(pose,route)
        polyline+=route;legs.append([list(q) for q in route]);waypoints.append(list(goal))
        last=route[-2] if len(route)>1 else pose
        pose=[*goal,math.atan2(goal[1]-last[1],goal[0]-last[0])]
        visited.append(pose)
    else:reason='WAYPOINT_LIMIT'
    if not waypoints:raise ValueError('DECLARED_ROUTE_NO_REACHABLE_WAYPOINT:'+str(reason))
    returning=route_to(pose,start[:2],geometry,observed_cells=observed_cells,clearance_m=clearance)
    polyline+=returning;legs.append([list(q) for q in returning])
    return dict(start=list(start),waypoints=waypoints,polyline=[list(p) for p in polyline],legs=legs,
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


def plan_pose(start,odom_origin,odom):
    """Odometry pose expressed in the plan frame, anchored at the declared start."""
    dx,dy=odom[0]-odom_origin[0],odom[1]-odom_origin[1];c,s=math.cos(-odom_origin[2]),math.sin(-odom_origin[2])
    lx,ly=dx*c-dy*s,dx*s+dy*c;c,s=math.cos(start[2]),math.sin(start[2])
    return [start[0]+lx*c-ly*s,start[1]+lx*s+ly*c,_wrap(start[2]+odom[2]-odom_origin[2])]


def next_move(pose,target,*,max_leg_m=MAX_LEG_M):
    """One finite step toward target from the measured (odometry) pose; None when reached.

    Re-aiming from the measured pose after every leg removes the robot's
    systematic curve instead of letting it accumulate over the route.
    """
    distance=math.dist(pose[:2],target[:2])
    if distance<ARRIVED_M:return None
    delta=_wrap(math.atan2(target[1]-pose[1],target[0]-pose[0])-pose[2])
    if abs(delta)>=HEADING_TOLERANCE_RAD:return dict(direction='left' if delta>0 else 'right',amount=abs(delta))
    return dict(direction='forward',amount=min(distance,max_leg_m))


def heading_move(pose,yaw):
    delta=_wrap(yaw-pose[2])
    return dict(direction='left' if delta>0 else 'right',amount=abs(delta)) if abs(delta)>=HEADING_TOLERANCE_RAD else None


def replan_legs(pose,goals,geometry,observed_cells=None,*,kind='physical',discs=()):
    """Fresh model paths from the measured pose through the remaining goals (with new keepout discs)."""
    clearance=max(task_clearance(kind,planning=True),PHYSICAL_ROUTE_CLEARANCE_M if kind=='physical' else 0.)
    legs=[];at=list(pose)
    for goal in goals:
        legs.append([list(q) for q in route_to(at,goal[:2],geometry,observed_cells=observed_cells,discs=discs,clearance_m=clearance)])
        at=[*goal[:2],0.]
    return legs


def move_text(step):
    """Exact text accepted by the existing finite-command parser."""
    if step['direction'] in ('forward','backward'):return '%s %.1fcm'%(step['direction'],step['amount']*100)
    return '%s %.2f degrees'%(step['direction'],math.degrees(step['amount']))


def integrate(start,steps):
    x,y,yaw=start
    for s in steps:
        if s['direction']=='forward':x+=s['amount']*math.cos(yaw);y+=s['amount']*math.sin(yaw)
        else:yaw=_wrap(yaw+(s['amount'] if s['direction']=='left' else -s['amount']))
    return [x,y,yaw]


__all__=['SCOPE','plan_survey','compile_moves','move_text','integrate','plan_pose','next_move','heading_move','replan_legs','NoBoundedPath']
