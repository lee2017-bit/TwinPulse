# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Narrow host-pinned pose repair, not general edit or geometry authority."""
from copy import deepcopy
import math

from .errors import InvalidProviderResponseError


def pose_pin(context, candidate):
    """Only unchanged-size existing furniture/recipe moves can enter this lane.

    The first interpretation is NOT proven correct by this pin. It prevents a
    repair from changing target/action/recipe/size/support/floor or abandoning
    its interpreted orientation. Geometry repairs translate existing centres.
    Normal dependency propagation still moves attached children in the App.
    """
    patch=candidate.get('patch')
    if candidate.get('mode')!='dependency' or not isinstance(patch,dict):return None
    if set(patch)!={'patch_version','edits'} or not patch['edits']:return None
    current={c['arguments']['id']:c for c in context['current_plan']['calls']}
    pinned=[]
    for edit in patch['edits']:
        if (set(edit)!={'action','target_id','reason','tool_call'} or edit['action']!='change'
                or edit['target_id'] not in current):return None
        old=deepcopy(current[edit['target_id']]);new=deepcopy(edit['tool_call'])
        yaw=new.get('arguments',{}).get('yaw_deg')
        if old['tool'] not in {'place_furniture','place_model_recipe'}:return None
        for call in (old,new):
            args=call.get('arguments',{})
            if 'center_m' not in args or 'yaw_deg' not in args:return None
            args.pop('center_m');args.pop('yaw_deg')
        if old!=new:return None
        old['arguments']['yaw_deg']=yaw
        pinned.append(dict(action='change',target_id=edit['target_id'],tool_call=old))
    if len({r['target_id'] for r in pinned})!=len(pinned):return None
    return dict(patch_version=patch['patch_version'],edits=sorted(pinned,key=lambda r:r['target_id']))


def require_same_pose_pin(context, candidate, pin):
    if pose_pin(context,candidate)!=pin:
        error=InvalidProviderResponseError('FEEDBACK_POSE_REPAIR_SCOPE_CHANGED: keep the first proposed orientation; only the original target centres may be corrected')
        error.code='FEEDBACK_POSE_REPAIR_SCOPE_CHANGED'
        raise error


def clearance_violation(diagnosis):
    """Only the typed candidate floor/footprint predicates can request HTTP."""
    if isinstance(diagnosis,dict) and diagnosis.get('code')=='FURNITURE_FOOTPRINT_OVERLAP':
        if (set(diagnosis)!={'code','groups','footprint_bounds_xy'} or not isinstance(diagnosis['groups'],list)
                or len(diagnosis['groups'])!=2 or any(not isinstance(g,str) for g in diagnosis['groups'])):
            raise ValueError('Invalid feedback overlap identities')
        rows=diagnosis['footprint_bounds_xy']
        if (not isinstance(rows,list) or len(rows)!=2 or any(not isinstance(v,list) or len(v)!=4 or
                any(type(n) not in (int,float) or not math.isfinite(n) for n in v) for v in rows)):
            raise ValueError('Invalid feedback overlap bounds')
        a,b=rows
        # Minimum axis translation to separate, not intersection width (which
        # is constant while a smaller rectangle remains contained).
        return max(0,min(a[1]-b[0],b[1]-a[0],a[3]-b[2],b[3]-a[2]))
    if (not isinstance(diagnosis,dict) or set(diagnosis)!={'code','group','footprint_bounds_xy','usable_floor_bounds_xy'}
            or diagnosis['code']!='FURNITURE_FLOOR_CLEARANCE' or not isinstance(diagnosis['group'],str)):
        raise ValueError('Unsupported feedback candidate diagnosis')
    bounds=diagnosis['footprint_bounds_xy'];usable=diagnosis['usable_floor_bounds_xy']
    if any(not isinstance(v,list) or len(v)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in v)
            for v in (bounds,usable)):
        raise ValueError('Invalid feedback candidate bounds')
    return max(0,usable[0]-bounds[0],bounds[1]-usable[1],usable[2]-bounds[2],bounds[3]-usable[3])
