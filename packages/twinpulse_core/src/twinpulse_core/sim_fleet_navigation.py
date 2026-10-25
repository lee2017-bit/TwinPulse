# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded scene-object approach for Isaac kinematic SIM only.

Pure data in/out, no transport, USD, model calls or physical authority. Uses
actual caller-supplied scene geometry, never photo-specific coordinates.
"""
import math
import re
from .bounded_grid_plan import plan_bounded_grid, NoBoundedPath


KINDS={'bed':'침대','chair':'의자','desk':'책상','sofa':'소파','table':'테이블',
       'wardrobe':'옷장','storage':'수납장','shelf':'선반'}


def destination_intent(text):
    value=text.strip().lower()
    if re.search(r'\b(?:move|place|shift|reposition)\s+(?:(?:the|this|that)\s+)?(?:'+ '|'.join(KINDS)+r')\b',value):return None
    if not (re.search(r'\b(?:go|navigate|drive|move|head|approach)\b.{0,100}?\b(?:to|towards?|near|nearest)\b',value)
            or re.search(r'(?:으로|쪽으로|근처로|가까이|로)\s*(?:가줘|가자|가|이동|움직)',value)):
        return None
    kinds=[kind for kind,alias in KINDS.items() if re.search(r'\b'+kind+r'\b',value) or alias in value]
    if len(kinds)>1:raise ValueError('NAVIGATION_TARGET_AMBIGUOUS')
    return dict(action='navigate',target_kind=kinds[0]) if kinds else None


def _checked_box(box):
    return (isinstance(box,(list,tuple)) and len(box)==4 and
            all(type(n) in (int,float) and math.isfinite(n) for n in box)
            and box[0]<box[2] and box[1]<box[3])


def checked_scene_geometry(value):
    """Copied current USD geometry, usable for planning, not physical truth."""
    from copy import deepcopy
    legacy={'epoch','targets','bounds','obstacles'}
    imported=legacy|{'schema','source_sha256','scene_revision','units_basis','meters_per_unit','grid'}
    if (not isinstance(value,dict) or set(value) not in (legacy,imported)
            or type(value['epoch']) is not int or value['epoch']<0 or not _checked_box(value['bounds'])
            or not isinstance(value['targets'],list) or len(value['targets'])>128
            or not isinstance(value['obstacles'],list) or len(value['obstacles'])>128
            or any(not _checked_box(b) for b in value['obstacles'])):return None
    for target in value['targets']:
        if (not isinstance(target,dict) or set(target)!={'id','kind','label','bounds'}
                or any(not isinstance(target[k],str) or len(target[k])>160 for k in ('id','kind','label'))
                or not _checked_box(target['bounds'])):return None
    if set(value)==imported:
        if (value['schema']!='scene-navigation-2.0' or value['units_basis'] not in {'authored','selected_for_sim'}
                or type(value['meters_per_unit']) not in (int,float) or value['meters_per_unit'] not in {1.,.01,.001}
                or any(not isinstance(value[k],str) or not re.fullmatch('[a-f0-9]{64}',value[k])
                    for k in ('source_sha256','scene_revision'))):return None
        try:
            from .navigation_grid import checked_navigation_grid
            checked_navigation_grid(value['grid'],value['bounds'])
        except (ValueError,TypeError,KeyError):return None
    return deepcopy(value)


def approach_plan(start,kind,targets,bounds,obstacles,discs=(),*,observed_cells=None,clearance_m=.25):
    """Nearest semantic object, reachable exterior standoff, exact goal endpoint.

    No fallback to a farther object if the nearest is blocked. Fixed candidate,
    grid, expansion and waypoint budgets. Unknown/missing geometry is rejected.
    """
    # Explicit task callers may use the user-selected 15cm envelope. Retain the
    # existing 25cm default for standalone callers and all other validation.
    if (type(clearance_m) not in (int,float) or not .15<=clearance_m<=.50 or kind not in KINDS or not isinstance(start,(list,tuple)) or len(start)!=3
            or any(type(n) not in (int,float) or not math.isfinite(n) for n in start)
            or not _checked_box(bounds) or not isinstance(targets,list) or len(targets)>128
            or not isinstance(obstacles,list) or len(obstacles)>128 or any(not _checked_box(b) for b in obstacles)):
        raise ValueError('NAVIGATION_SCENE_INVALID')
    candidates=[t for t in targets if t.get('kind')==kind and isinstance(t.get('id'),str)
                and _checked_box(t.get('bounds'))]
    if not candidates:raise ValueError('NAVIGATION_TARGET_MISSING')
    def gap(t):
        a,b,c,d=t['bounds'];return math.hypot(max(a-start[0],0,start[0]-c),max(b-start[1],0,start[1]-d))
    candidates.sort(key=lambda t:(gap(t),t['id']))
    if len(candidates)>1 and abs(gap(candidates[0])-gap(candidates[1]))<.01:
        raise ValueError('NAVIGATION_TARGET_AMBIGUOUS')
    target=candidates[0];a,b,c,d=target['bounds'];margin=clearance_m+.03
    goals=[]
    for f in (.5,.25,.75,.0,1.):
        goals.extend([(a-margin,b+(d-b)*f),(c+margin,b+(d-b)*f),
                      (a+(c-a)*f,b-margin),(a+(c-a)*f,d+margin)])
    goals.sort(key=lambda p:math.dist(p,start[:2]))
    boxes=[((a+c)/2,(b+d)/2,(c-a)/2,(d-b)/2,0.) for a,b,c,d in obstacles]
    for goal in goals:
        try:
            route=plan_bounded_grid(start[:2],goal,(bounds[0],bounds[2],bounds[1],bounds[3]),
                boxes,discs,resolution=.10,clearance=clearance_m,observed_cells=observed_cells)
        except NoBoundedPath:continue
        length=sum(math.dist(x,y) for x,y in zip([start[:2],*route],route))
        if length>5.:continue  # Bounded SIM instruction, never an unbounded mission.
        return dict(target_id=target['id'],target_label=target.get('label',kind),target_kind=kind,
                    target_bounds=list(target['bounds']),goal_xy=list(goal),waypoints=[list(p) for p in route],
                    path_length_m=length,clearance_m=clearance_m,source='current_isaac_usd_geometry',physical_authority=False)
    raise ValueError('NAVIGATION_NO_REACHABLE_APPROACH')


def next_leg(pose,waypoints,index):
    while index<len(waypoints) and math.dist(pose[:2],waypoints[index])<=.015:index+=1
    if index==len(waypoints):return None,0.,index
    x,y=waypoints[index];error=math.atan2(math.sin(math.atan2(y-pose[1],x-pose[0])-pose[2]),
                                       math.cos(math.atan2(y-pose[1],x-pose[0])-pose[2]))
    if abs(error)>.04:return ('left' if error>0 else 'right'),abs(error),index
    return 'forward',math.dist(pose[:2],waypoints[index]),index


def checked_navigation_report(value,task_id):
    """Bound engine-to-UI diagnostics; never motion authority or a saved lease."""
    import json
    if (not isinstance(value,dict) or value.get('request_id')!=task_id
            or value.get('state') not in {'PLANNING','RUNNING','ARRIVED','FAILED'}
            or set(value)-{'request_id','state','target_id','target_label','target_kind','goal_xy','waypoints','path_length_m','clearance_m','remaining_m','waypoint_index','reason'}):return None
    try:
        if len(json.dumps(value,allow_nan=False))>6000:return None
    except (ValueError,TypeError):return None
    for key in ('target_id','target_label','target_kind','reason'):
        if key in value and value[key] is not None and (not isinstance(value[key],str) or len(value[key])>160):return None
    if not isinstance(value.get('waypoints',[]),list):return None
    points=([value['goal_xy']] if 'goal_xy' in value else [])+value.get('waypoints',[])
    if len(points)>17 or any(not isinstance(p,list) or len(p)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>1000 for n in p) for p in points):return None
    for key in ('path_length_m','remaining_m','clearance_m','waypoint_index'):
        if key in value and (type(value[key]) not in (int,float) or not math.isfinite(value[key]) or not 0<=value[key]<=10000):return None
    return dict(value)
