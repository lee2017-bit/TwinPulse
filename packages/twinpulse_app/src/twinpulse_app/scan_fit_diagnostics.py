# SPDX-License-Identifier: Apache-2.0
"""Bounded OFFLINE scan diagnostics, independent of wheel input.

Live field_tests.register_pair is deliberately unchanged. Point-to-segment
fits avoid a demonstrated fixed-angle, point-to-point sampling bias, but remain
local hypotheses. Low residual alone is not chassis or world-pose proof.
"""
import math
import time


def uniform_ring(points,limit):
    if type(limit) is not int or limit<3:raise ValueError('DIAGNOSTIC_SAMPLE_BOUND')
    count=min(len(points),limit)
    return [list(points[i*len(points)//count]) for i in range(count)]


def _solve(matrix,rhs):
    rows=[list(a)+[b] for a,b in zip(matrix,rhs)];scale=max(abs(v) for row in matrix for v in row)
    for i in range(3):
        pivot=max(range(i,3),key=lambda j:abs(rows[j][i]))
        if abs(rows[pivot][i])<max(1e-9,scale*1e-7):raise ValueError('DIAGNOSTIC_GEOMETRY_DEGENERATE')
        rows[i],rows[pivot]=rows[pivot],rows[i];v=rows[i][i];rows[i]=[n/v for n in rows[i]]
        for j in range(3):
            if j!=i:
                v=rows[j][i];rows[j]=[a-v*b for a,b in zip(rows[j],rows[i])]
    return [row[3] for row in rows]


def segment_fit(before,after,*,deadline):
    if time.monotonic()>deadline:raise ValueError('DIAGNOSTIC_DEADLINE')
    if not 40<=len(before)<=4096 or not 40<=len(after)<=4096:raise ValueError('DIAGNOSTIC_POINT_BOUND')
    if any(len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in [*before,*after]):
        raise ValueError('DIAGNOSTIC_POINTS_INVALID')
    p=uniform_ring(sorted(before,key=lambda p:math.atan2(p[1],p[0])),400)
    q=uniform_ring(after,160);segments=[];cells={};cell=.3
    for a,b in zip(p,p[1:]+p[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if not .005<=length<=.35:continue  # Never join a doorway/occlusion gap.
        index=len(segments);segments.append((a,b,dx,dy,length))
        for ix in range(math.floor(min(a[0],b[0])/cell),math.floor(max(a[0],b[0])/cell)+1):
            for iy in range(math.floor(min(a[1],b[1])/cell),math.floor(max(a[1],b[1])/cell)+1):
                cells.setdefault((ix,iy),[]).append(index)
    if len(segments)<20:raise ValueError('DIAGNOSTIC_SEGMENTS_INSUFFICIENT')

    def pairs(x,y,yaw):
        c,s=math.cos(yaw),math.sin(yaw);result=[]
        for index,(u,v) in enumerate(q):
            if index%16==0 and time.monotonic()>deadline:raise ValueError('DIAGNOSTIC_DEADLINE')
            rx=c*u-s*v;ry=s*u+c*v;wx=rx+x;wy=ry+y;ix=math.floor(wx/cell);iy=math.floor(wy/cell)
            best=None;distance=.2**2
            for identity in {i for gx in (ix-1,ix,ix+1) for gy in (iy-1,iy,iy+1) for i in cells.get((gx,gy),[])}:
                a,b,dx,dy,length=segments[identity];t=((wx-a[0])*dx+(wy-a[1])*dy)/length**2
                if not 0.<=t<=1.:continue
                nx,ny=-dy/length,dx/length;error=nx*(wx-a[0])+ny*(wy-a[1])
                if error*error<distance:
                    distance=error*error;best=(error,(nx,ny,-nx*ry+ny*rx))
            if best is not None:result.append(best)
        return sorted(result,key=lambda pair:abs(pair[0]))

    candidates=[]
    for seed in (0.,-.12,.12):
        x=y=0.;yaw=seed;converged=False
        for iteration in range(24):
            if time.monotonic()>deadline:raise ValueError('DIAGNOSTIC_DEADLINE')
            matched=pairs(x,y,yaw)
            if len(matched)<max(30,len(q)//2):break
            retained=matched[:max(30,int(.85*len(matched)))];matrix=[[0.]*3 for _ in range(3)];rhs=[0.]*3
            for error,jacobian in retained:
                weight=min(1.,.03/max(abs(error),1e-12))
                for i in range(3):
                    rhs[i]-=weight*jacobian[i]*error
                    for j in range(3):matrix[i][j]+=weight*jacobian[i]*jacobian[j]
            try:delta=_solve(matrix,rhs)
            except ValueError:break
            if math.hypot(*delta[:2])>.2 or abs(delta[2])>.15:break
            x+=delta[0];y+=delta[1];yaw+=delta[2]
            if math.hypot(*delta[:2])<1e-5 and abs(delta[2])<1e-5:converged=True;break
        final=pairs(x,y,yaw)
        if time.monotonic()>deadline:raise ValueError('DIAGNOSTIC_DEADLINE')
        if not converged or len(final)<max(30,len(q)//2):continue
        retained=final[:max(30,int(.85*len(final)))];residual=math.sqrt(sum(e*e for e,_ in retained)/len(retained))
        candidates.append(dict(delta=[x,y,yaw],residual_m=residual,matched_points=len(final),
            sampled_points=len(q),converged=converged,iterations=iteration+1))
    if not candidates:raise ValueError('DIAGNOSTIC_NONCONVERGED_OR_DEGENERATE')
    candidates.sort(key=lambda v:v['residual_m']);best=candidates[0]
    for other in candidates[1:]:
        if (other['residual_m']<=best['residual_m']+.003 and
                (math.dist(other['delta'][:2],best['delta'][:2])>.025 or abs(other['delta'][2]-best['delta'][2])>.04)):
            raise ValueError('DIAGNOSTIC_COMPETING_LOCAL_FITS')
    if time.monotonic()>deadline:raise ValueError('DIAGNOSTIC_DEADLINE')
    return dict(best,status='LOCAL_FIT_UNQUALIFIED',method='POINT_TO_SEGMENT_OFFLINE_1',
        residual_basis='RECOMPUTED_AT_RETURNED_TRANSFORM_TRIMMED_85_PERCENT',physical_motion_verified=False,
        full_revolution_observable=False)
