# SPDX-License-Identifier: Apache-2.0
"""Conservative intersection, never turns USD priors into measurements."""
from copy import deepcopy
import math
from .room_localization import compose

def intersect_model_free(local_rows,world_rows,world_from_local,resolution=.1):
    if not isinstance(local_rows,list) or not isinstance(world_rows,list) or len(local_rows)>18000 or len(world_rows)>10000:
        raise ValueError('REGISTERED_GRID_BOUND')
    states={}
    for row in world_rows:
        key=tuple(math.floor(v/resolution) for v in row[:2]);state=row[2]
        states[key]=state if key not in states or states[key]==state else 'unknown'
    result=[]
    for row in local_rows:
        checked=deepcopy(row)
        if row[2]=='free':
            ix,iy=(math.floor(v/resolution) for v in row[:2])
            corners=[compose(world_from_local,[x*resolution,y*resolution,0.]) for x,y in ((ix,iy),(ix+1,iy),(ix,iy+1),(ix+1,iy+1))]
            lo=[min(p[i] for p in corners) for i in (0,1)];hi=[max(p[i] for p in corners) for i in (0,1)]
            # Every grid square touching the rotated square's AABB must be
            # free. Deliberately conservative; a center-only projection would
            # erase thin walls/keepouts and create false traversable space.
            x0,y0=[math.floor((n-1e-10)/resolution) for n in lo];x1,y1=[math.floor((n+1e-10)/resolution) for n in hi]
            if any(states.get((x,y))!='free' for x in range(x0,x1+1) for y in range(y0,y1+1)):checked[2]='unknown'
        result.append(checked)
    return result
