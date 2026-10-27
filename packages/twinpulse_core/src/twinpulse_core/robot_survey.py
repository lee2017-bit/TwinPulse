# SPDX-License-Identifier: Apache-2.0
"""Bounded observation-location coverage on caller-supplied current geometry.

No model coordinates or fixed room circuit. Unknown cells stay blocked. This
does not assert that a scan source contains every real obstacle or room.
"""
import math
from .bounded_grid_plan import plan_bounded_grid, NoBoundedPath

# User-selected task envelope (2026-10-25); not a measured physical footprint
# or a change to robot-side braking/sensor protections.
MIN_CLEARANCE_M=.15
PLANNING_MARGIN_M=.02
PLANNING_CLEARANCE_M=MIN_CLEARANCE_M+PLANNING_MARGIN_M
ROUTE_TURN_TOLERANCE_RAD=.001
# Existing SIM executor protection, shared without weakening it. User task
# clearance is a minimum; a driver may require a larger reference envelope.
SIM_BODY_RADIUS_M=.105
SIM_STOP_SKIN_M=.10
SIM_STOP_SUBSTEP_TRAVEL_M=.05*.05
SIM_EXECUTOR_REFERENCE_CLEARANCE_M=SIM_BODY_RADIUS_M+SIM_STOP_SKIN_M+SIM_STOP_SUBSTEP_TRAVEL_M


def task_clearance(kind,*,planning=False):
    effective=max(MIN_CLEARANCE_M,SIM_EXECUTOR_REFERENCE_CLEARANCE_M) if kind=='sim' else MIN_CLEARANCE_M
    return effective+(PLANNING_MARGIN_M if planning else 0.)


def route_to(pose, goal, geometry, *, observed_cells=None, discs=(),clearance_m=PLANNING_CLEARANCE_M,home=None):
    a,b,c,d=geometry['bounds']
    boxes=[((x+z)/2,(y+w)/2,(z-x)/2,(w-y)/2,0.) for x,y,z,w in geometry['obstacles']]
    return [list(p) for p in plan_bounded_grid(pose[:2],goal,(a,c,b,d),boxes,discs,
        resolution=.1,clearance=clearance_m,observed_cells=observed_cells,home=None if home is None else tuple(home[:2]))]


def checked_motion_segment(pose,direction,amount,geometry,*,observed_cells=None,discs=(),clearance_m=MIN_CLEARANCE_M):
    """Check the actual serialized primitive, not an ideal path waypoint.

    Use the task envelope and unchanged unknown-cell rules. The nominal planner
    adds 2cm to avoid tangent waypoints; this is not a collision epsilon or snap.
    """
    distance=amount*(1 if direction=='forward' else -1) if direction in {'forward','backward'} else 0.
    endpoint=[pose[0]+distance*math.cos(pose[2]),pose[1]+distance*math.sin(pose[2])]
    a,b,c,d=geometry['bounds']
    boxes=[((x+z)/2,(y+w)/2,(z-x)/2,(w-y)/2,0.) for x,y,z,w in geometry['obstacles']]
    plan_bounded_grid(pose[:2],endpoint,(a,c,b,d),boxes,discs,resolution=.1,
        clearance=clearance_m,observed_cells=observed_cells,checked_route=[endpoint])
    return endpoint


def route_length(start, route):return sum(math.dist(a,b) for a,b in zip([start[:2],*route],route))


def execution_cost(pose,route,*,final_yaw=None,linear_speed_m_s=.05,angular_speed_rad_s=.30,turn_tolerance_rad=ROUTE_TURN_TOLERANCE_RAD):
    """Conservative reservation for .4m/pi segments, scans and turn time."""
    position=list(pose);segments=0;duration=0.
    for goal in route:
        distance=math.dist(position[:2],goal)
        if distance<.015:continue
        heading=math.atan2(goal[1]-position[1],goal[0]-position[0])
        turn=abs(math.atan2(math.sin(heading-position[2]),math.cos(heading-position[2])))
        turns=math.ceil(turn/math.pi) if turn>turn_tolerance_rad else 0
        travel=math.ceil(distance/.40)
        segments+=turns+travel
        duration+=distance/linear_speed_m_s+turn/angular_speed_rad_s+(turns+travel)*4.5
        position=[*goal,heading]
    if final_yaw is not None:
        turn=abs(math.atan2(math.sin(final_yaw-position[2]),math.cos(final_yaw-position[2])))
        if turn>.04:
            segments+=1;duration+=turn/angular_speed_rad_s+4.5;position[2]=final_yaw
    return dict(segments=segments,duration_s=duration,end_pose=position)


def observation_candidates(geometry):
    a,b,c,d=geometry['bounds'];spacing=.65
    nx=math.ceil((c-a)/spacing);ny=math.ceil((d-b)/spacing)
    if nx*ny>1024:raise ValueError('SURVEY_GRID_BUDGET')
    return [[a+.35+ix*spacing,b+.35+iy*spacing] for ix in range(nx) for iy in range(ny)
            if a+.35+ix*spacing<c-.30 and b+.35+iy*spacing<d-.30]


def next_observation(pose, start, visited, geometry, distance_remaining, *, return_required, observed_cells=None, discs=(),clearance_m=PLANNING_CLEARANCE_M):
    """Replan against the current map, reserving a checked return path.

    No candidate is not a certificate of complete physical-room coverage. The
    result explicitly reports the bounded known-geometry scope and reason.
    """
    candidates=observation_candidates(geometry)
    novel=[p for p in candidates if all(math.dist(p,q[:2])>.50 for q in visited)]
    novel.sort(key=lambda p:(math.dist(p,pose[:2]),p))
    checked=0
    for goal in novel[:32]:
        checked+=1
        try:
            route=route_to(pose,goal,geometry,observed_cells=observed_cells,discs=discs,clearance_m=clearance_m)
            returning=route_to([*goal,0.],start[:2],geometry,observed_cells=observed_cells,discs=discs,clearance_m=clearance_m) if return_required else []
        except NoBoundedPath:continue
        length=route_length(pose,route);reserved=route_length(goal,returning) if returning else 0.
        if length+reserved+.25>distance_remaining:continue
        return dict(route=route,goal=goal,candidates=len(candidates),unvisited=len(novel),checked=checked,
                    reserved_return_m=reserved,scope='BOUNDED_CURRENT_GEOMETRY_NOT_WHOLE_ROOM_PROOF')
    return dict(route=None,goal=None,candidates=len(candidates),unvisited=len(novel),checked=checked,
                reason='KNOWN_LOCATIONS_VISITED' if not novel else 'NO_REACHABLE_LOCATION_WITH_RETURN_BUDGET',
                scope='BOUNDED_CURRENT_GEOMETRY_NOT_WHOLE_ROOM_PROOF')
