# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded horizontal geometric LiDAR. No device, USD, motion or time authority.

Triangle/plane sections preserve legs, openings and rotated furniture instead of
using an object's filled AABB as a sensor target. This is not an optical model.
"""
import math


def slice_triangle(triangle, height):
    hits=[]
    for a,b in zip(triangle,(*triangle[1:],triangle[0])):
        da,db=a[2]-height,b[2]-height
        if abs(da)<1e-9: hits.append(tuple(a[:2]))
        if da*db<0:
            t=da/(da-db);hits.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
    unique=list(dict.fromkeys(hits))
    if len(unique)<2:return []
    # Coplanar faces contribute their edges; never invent filled height columns.
    if len(unique)==3:return list(zip(unique,(*unique[1:],unique[0])))
    return [(unique[0],unique[1])]


def _build_section_index(items):
    # Module recursion does not create a self-referencing closure per index.
    if not items:return None
    bounds=(min(min(a[0],b[0]) for a,b in items),min(min(a[1],b[1]) for a,b in items),
            max(max(a[0],b[0]) for a,b in items),max(max(a[1],b[1]) for a,b in items))
    if len(items)<=8:return bounds,items,None,None
    axis=0 if bounds[2]-bounds[0]>=bounds[3]-bounds[1] else 1
    items=sorted(items,key=lambda s:s[0][axis]+s[1][axis]);mid=len(items)//2
    return bounds,None,_build_section_index(items[:mid]),_build_section_index(items[mid:])


class SectionIndex:
    def __init__(self,segments):
        if len(segments)>100000:raise ValueError('LIDAR_SECTION_BUDGET')
        self.count=len(segments);self.root=_build_section_index(segments)

    def cast(self,origin,direction,maximum=8.,*,cancel=None):
        best=maximum
        # A nested recursive visit function kept a function/cell cycle alive
        # for every ray. Preserve left-first DFS without per-ray cycles or any
        # GC scheduling changes; first-hit geometry/epsilons remain identical.
        nodes=[self.root]
        while nodes:
            node=nodes.pop()
            if cancel is not None and cancel():raise ValueError('LIDAR_SCAN_CANCELLED')
            if node is None:continue
            (x0,y0,x1,y1),items,left,right=node;enter,leave=0.,best
            intersects=True
            for o,d,lo,hi in zip(origin,direction,(x0,y0),(x1,y1)):
                if abs(d)<1e-12:
                    if not lo-1e-9<=o<=hi+1e-9:intersects=False;break
                else:
                    a,b=(lo-o)/d,(hi-o)/d
                    enter=max(enter,min(a,b));leave=min(leave,max(a,b))
                    if leave+1e-9<enter:intersects=False;break
            if not intersects:continue
            if items is None:nodes.append(right);nodes.append(left);continue
            dx,dy=direction
            for a,b in items:
                sx,sy=b[0]-a[0],b[1]-a[1];den=dx*sy-dy*sx
                if abs(den)<1e-12:continue
                ax,ay=a[0]-origin[0],a[1]-origin[1]
                t=(ax*sy-ay*sx)/den;u=(ax*dy-ay*dx)/den
                if 1e-7<t<best and -1e-9<=u<=1+1e-9:best=t
        return best

    def scan(self,pose,maximum=8.,samples=180,*,cancel=None):
        x,y,yaw=pose;points=[]
        for index in range(samples):
            if cancel is not None and cancel():raise ValueError('LIDAR_SCAN_CANCELLED')
            angle=index*math.tau/samples
            direction=(math.cos(angle+yaw),math.sin(angle+yaw))
            distance=self.cast((x,y),direction,maximum,cancel=cancel)
            if distance<maximum:points.append([round(distance*math.cos(angle),4),round(distance*math.sin(angle),4)])
        return points
