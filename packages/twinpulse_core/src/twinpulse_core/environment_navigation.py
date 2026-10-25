# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Conservative cells from actual floor triangles and robot-height geometry."""
import math


def clip(poly,axis,value,positive):
    out=[]
    if not poly:return out
    previous=poly[-1];old=(previous[axis]>=value if positive else previous[axis]<=value)
    for point in poly:
        new=(point[axis]>=value if positive else point[axis]<=value)
        if new!=old:
            t=(value-previous[axis])/(point[axis]-previous[axis])
            out.append([a+(b-a)*t for a,b in zip(previous,point)])
        if new:out.append(point)
        previous=point;old=new
    return out


def area(poly):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1])))/2 if len(poly)>2 else 0.


def convex_overlap_area(left,right):
    """Positive-area intersection; shared triangle edges are not overlaps."""
    if area(left)<1e-12 or area(right)<1e-12:return 0.
    if any(max(p[i] for p in left)<=min(p[i] for p in right)+1e-12 or
           max(p[i] for p in right)<=min(p[i] for p in left)+1e-12 for i in (0,1)):return 0.
    orientation=1 if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(right,right[1:]+right[:1]))>0 else -1
    poly=left
    for a,b in zip(right,right[1:]+right[:1]):
        if not poly:break
        out=[];previous=poly[-1]
        def side(p):return orientation*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
        old=side(previous)
        for point in poly:
            new=side(point)
            if (new>=0)!=(old>=0):
                t=old/(old-new);out.append([x+(y-x)*t for x,y in zip(previous,point)])
            if new>=0:out.append(point)
            previous=point;old=new
        poly=out
    return area(poly)


def navigation_cells(meshes,resolution=.1,*,keepout_polygons=()):
    floor=[];obstacles=[];targets=[]
    for mesh in meshes:
        points=mesh['points_m'];delta=mesh.get('translation_m',[0,0,0])
        points=[[p[i]+delta[i] for i in range(3)] for p in points]
        if mesh['category'] in {'sofa','table','chair','storage','refrigerator'}:
            targets.append(dict(id=mesh['id'],kind=mesh['category'],label=mesh['label'],
                bounds=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]))
        for t in mesh['triangles']:
            poly=[points[i] for i in t]
            if mesh['category']=='floor':
                if max(abs(p[2]) for p in poly)<1e-4 and area(poly)>1e-10:floor.append(poly)
            elif mesh.get('synthetic_keepout',False):
                # Fill the complete conservative box footprint, including its
                # interior, even when top/bottom lie outside the height slice.
                obstacles.append([[p[0],p[1],.175] for p in poly])
            else:
                poly=clip(clip(poly,2,.005,True),2,.30,False)
                if poly:obstacles.append(poly)
    obstacles.extend(keepout_polygons)
    if not floor:raise ValueError('ENVIRONMENT_FLAT_FLOOR_REQUIRED')
    all_points=[p for poly in floor for p in poly]
    ix0=math.floor(min(p[0] for p in all_points)/resolution)-1
    iy0=math.floor(min(p[1] for p in all_points)/resolution)-1
    ix1=math.ceil(max(p[0] for p in all_points)/resolution)+1
    iy1=math.ceil(max(p[1] for p in all_points)/resolution)+1
    if (ix1-ix0)*(iy1-iy0)>10000:raise ValueError('ENVIRONMENT_NAVIGATION_CELL_BUDGET')
    coverage={};blocked=set();pieces={};ambiguous=set()
    def each_cell(poly):
        a=max(ix0,math.floor(min(p[0] for p in poly)/resolution-1e-8))
        b=min(ix1-1,math.floor(max(p[0] for p in poly)/resolution+1e-8))
        c=max(iy0,math.floor(min(p[1] for p in poly)/resolution-1e-8))
        d=min(iy1-1,math.floor(max(p[1] for p in poly)/resolution+1e-8))
        for ix in range(a,b+1):
            for iy in range(c,d+1):
                clipped=poly
                for axis,v,side in [(0,ix*resolution,True),(0,(ix+1)*resolution,False),
                                    (1,iy*resolution,True),(1,(iy+1)*resolution,False)]:
                    clipped=clip(clipped,axis,v,side)
                if clipped:yield (ix,iy),clipped
    for poly in floor:
        for key,part in each_cell(poly):
            if area(part)<1e-12:continue
            prior=pieces.setdefault(key,[])
            if len(prior)>=128 or any(convex_overlap_area(part,p)>1e-10 for p in prior):ambiguous.add(key)
            elif key not in ambiguous:prior.append(part)
            coverage[key]=coverage.get(key,0.)+area(part)
    for poly in obstacles:
        for key,part in each_cell(poly):blocked.add(key)  # Includes vertical zero-area walls.
    free={key for key,value in coverage.items() if abs(value-resolution**2)<1e-8 and key not in blocked and key not in ambiguous}
    cells=[[(ix+.5)*resolution,(iy+.5)*resolution,'free' if (ix,iy) in free else 'occupied',0,0,0,0]
        for iy in range(iy0,iy1) for ix in range(ix0,ix1)]
    # Merge adjacent occupied runs into rectangles for the existing manual guard.
    rectangles=[];active={}
    for iy in range(iy0,iy1):
        runs=[];start=None
        for ix in range(ix0,ix1+1):
            occupied=ix<ix1 and (ix,iy) not in free
            if occupied and start is None:start=ix
            if not occupied and start is not None:runs.append((start,ix));start=None
        next_active={}
        for run in runs:
            row=active.pop(run,None) or [run[0]*resolution,iy*resolution,run[1]*resolution,(iy+1)*resolution]
            row[3]=(iy+1)*resolution;next_active[run]=row
        rectangles.extend(active.values());active=next_active
    rectangles.extend(active.values())
    x0,y0,x1,y1=ix0*resolution,iy0*resolution,ix1*resolution,iy1*resolution
    rectangles += [[-101.,-101.,x0,101.],[x1,-101.,101.,101.],[x0,-101.,x1,y0],[x0,y1,x1,101.]]
    if len(rectangles)>512:raise ValueError('ENVIRONMENT_COLLISION_CELL_BUDGET')
    return dict(targets=targets,bounds=[x0,y0,x1,y1],obstacles=[],cells=cells,manual_boxes=rectangles,
                source='current_environment_triangle_cells',resolution_m=resolution)
