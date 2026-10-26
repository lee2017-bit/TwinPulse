# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Bounded, versioned free-space mask. No transport or physical authority.

Only explicitly free cells are one bits. Missing/unknown/occupied cells stay
blocked. Decode at a geometry revision boundary, never on every control tick.
"""
import base64
import math
from .revisions import canonical_sha256


def encode_navigation_grid(cells, resolution=.1):
    if (not isinstance(cells,list) or not 1<=len(cells)<=40000
            or type(resolution) not in (int,float) or resolution!=.1):
        raise ValueError('NAVIGATION_GRID_INPUT')
    positions={}
    for row in cells:
        if (not isinstance(row,list) or len(row)!=7 or row[2] not in {'free','occupied','unknown'}
                or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>101 for v in row[:2])):
            raise ValueError('NAVIGATION_GRID_CELL')
        key=tuple(math.floor(v/resolution) for v in row[:2])
        if any(abs(row[i]-(key[i]+.5)*resolution)>1e-8 for i in (0,1)) or key in positions:
            raise ValueError('NAVIGATION_GRID_CENTER_OR_DUPLICATE')
        positions[key]=row[2]
    x0=min(k[0] for k in positions);y0=min(k[1] for k in positions)
    nx=max(k[0] for k in positions)-x0+1;ny=max(k[1] for k in positions)-y0+1
    if nx*ny!=len(positions):raise ValueError('NAVIGATION_GRID_COVERAGE')
    bits=bytearray((nx*ny+7)//8)
    for (x,y),state in positions.items():
        index=(y-y0)*nx+x-x0
        if state=='free':bits[index//8]|=1<<(index%8)
    result=dict(schema='navigation-grid-1.0',resolution_m=resolution,origin_cell=[x0,y0],size=[nx,ny],
                free_bits=base64.b64encode(bits).decode('ascii'))
    return dict(result,sha256=canonical_sha256(result))


def checked_navigation_grid(value,bounds=None):
    fields={'schema','resolution_m','origin_cell','size','free_bits','sha256'}
    if (not isinstance(value,dict) or set(value)!=fields or value['schema']!='navigation-grid-1.0'
            or type(value['resolution_m']) not in (int,float) or value['resolution_m']!=.1
            or not isinstance(value['origin_cell'],list) or len(value['origin_cell'])!=2
            or any(type(v) is not int or abs(v)>1010 for v in value['origin_cell'])
            or not isinstance(value['size'],list) or len(value['size'])!=2
            or any(type(v) is not int or not 1<=v<=40000 for v in value['size'])
            or value['size'][0]*value['size'][1]>40000
            or not isinstance(value['free_bits'],str) or len(value['free_bits'])>6700
            or not isinstance(value['sha256'],str)):
        raise ValueError('NAVIGATION_GRID_CONTRACT')
    data={k:v for k,v in value.items() if k!='sha256'}
    if canonical_sha256(data)!=value['sha256']:raise ValueError('NAVIGATION_GRID_DIGEST')
    try:bits=base64.b64decode(value['free_bits'],validate=True)
    except (ValueError,TypeError) as exc:raise ValueError('NAVIGATION_GRID_ENCODING') from exc
    total=math.prod(value['size'])
    if len(bits)!=(total+7)//8 or (total%8 and bits[-1]>>(total%8)):
        raise ValueError('NAVIGATION_GRID_PADDING')
    x,y=value['origin_cell'];nx,ny=value['size'];r=value['resolution_m']
    if bounds is not None and (len(bounds)!=4 or any(abs(a-b)>1e-8 for a,b in
            zip(bounds,[x*r,y*r,(x+nx)*r,(y+ny)*r]))):
        raise ValueError('NAVIGATION_GRID_BOUNDS')
    return bits


def decode_navigation_grid(value,bounds=None):
    bits=checked_navigation_grid(value,bounds);x,y=value['origin_cell'];nx,ny=value['size'];r=value['resolution_m']
    return [[(x+ix+.5)*r,(y+iy+.5)*r,'free' if bits[(iy*nx+ix)//8]&(1<<((iy*nx+ix)%8)) else 'occupied',0,0,0,0]
        for iy in range(ny) for ix in range(nx)]
