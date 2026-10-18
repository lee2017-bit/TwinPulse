# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded facts from actual box geometry, never a guessed functional front.

The same descriptor accompanies discovery, parameter planning and current-plan
review/repair. It does not rotate, replace, admit or modify any scene object.
"""
from copy import deepcopy
from math import cos, radians, sin

from twinpulse_core import canonical_sha256
from twinpulse_core.model_recipe import MAX_PARTS

REVISION = 'assembly-geometry-evidence-1.0'
INSTRUCTIONS = (
    'assembly_geometry is host-computed geometry, not measured source shape. '
    'Identify the owner and actual world normal of a tall boundary panel before judging facing. '
    'Local width is X and depth is Y; the long axis is not necessarily width. '
    'A least-covered boundary face is only an opening candidate, not a proven functional front. '
    'Compare source openings, back panels, usable support surfaces and achievable dimension domains. '
    'Yaw changes rotate the WHOLE actual assembly and do not exchange width/depth bounds. '
    'If source proportions and panel orientation cannot both be represented within the pinned '
    'recipe domain, request an eligible immutable recipe replacement, not an impossible pose-only fix. '
    'Never move a panel independently, silently clamp a long worktop, or infer support from its name. '
)


def _union_area(rectangles):
    """Exact union of every compiler-allowed expanded part face."""
    xs=sorted({v for r in rectangles for v in r[:2]})
    area=0.
    for lo,hi in zip(xs,xs[1:]):
        spans=sorted((r[2],r[3]) for r in rectangles if r[0]<hi and r[1]>lo)
        covered=0.;end=None
        for bottom,top in spans:
            covered+=max(0.,top-max(bottom,end if end is not None else bottom))
            end=max(top,end if end is not None else top)
        area+=(hi-lo)*covered
    return area


def describe(parts, dimensions, *, parameters=None, binding=None, yaw_deg=0, centre_xy=(0,0)):
    """Describe checked local boxes; source parts/definitions stay unmodified."""
    normalized=[dict(id=p['id'],center=deepcopy(p.get('center',p.get('center_m'))),
        size=deepcopy(p.get('size',p.get('size_m'))),support_top=bool(p.get('support_top',False))) for p in parts]
    if not 1<=len(normalized)<=MAX_PARTS:raise ValueError('ASSEMBLY_EVIDENCE_PART_COUNT')
    w,d,h=dimensions;angle=radians(yaw_deg);c,s=cos(angle),sin(angle)
    faces=[]
    for axis,extent,other in ((0,w,1),(1,d,0)):
        for sign in (-1,1):
            boundary=sign*extent/2;rects=[];owners=[]
            for p in normalized:
                if abs(p['center'][axis]+sign*p['size'][axis]/2-boundary)>1e-6:continue
                lo=p['center'][other]-p['size'][other]/2;hi=lo+p['size'][other]
                bottom=p['center'][2]-p['size'][2]/2;top=bottom+p['size'][2]
                rects.append((lo,hi,bottom,top));owners.append((p['size'][other]*p['size'][2],p['id']))
            normal=(sign*c,sign*s) if axis==0 else (-sign*s,sign*c)
            faces.append(dict(local_face=('x' if axis==0 else 'y')+('+' if sign==1 else '-'),
                world_outward_xy=[round(v,6) for v in normal],
                covered_area_ratio=round(_union_area(rects)/((d if axis==0 else w)*h),6),
                largest_boundary_part_ids=[i for _,i in sorted(owners,key=lambda row:(-row[0],row[1]))[:4]],
                boundary_part_count=len(owners)))
    def summary(p):
        x,y,z=p['center']
        return dict(id=p['id'],local_center_m=deepcopy(p['center']),size_m=deepcopy(p['size']),
            world_center_m=[round(centre_xy[0]+c*x-s*y,6),round(centre_xy[1]+s*x+c*y,6),z])
    vertical=sorted((p for p in normalized if p['size'][2]>=2*min(p['size'][:2])),
        key=lambda p:(-p['size'][2]*max(p['size'][:2]),p['id']))
    supports=sorted((p for p in normalized if p['support_top']),key=lambda p:(p['center'][2],p['id']))
    minimum=min(f['covered_area_ratio'] for f in faces)
    value=dict(schema_version=REVISION,binding=deepcopy(binding or {}),dimensions_m=list(dimensions),
        parameters=deepcopy(parameters),local_axes='X width, Y depth, Z bottom0 to height; yaw rotates all parts',
        yaw_deg=yaw_deg,centre_xy_m=list(centre_xy),part_count=len(normalized),side_faces=faces,
        least_covered_faces=[f['local_face'] for f in faces if abs(f['covered_area_ratio']-minimum)<1e-6],
        functional_front='unknown_not_inferred_from_boundary_coverage',
        major_vertical_parts=[summary(p) for p in vertical[:8]],
        vertical_parts_total=len(vertical),vertical_parts_truncated=len(vertical)>8,
        support_surfaces=[summary(p) for p in supports[:12]],
        support_surfaces_total=len(supports),support_surfaces_truncated=len(supports)>12,
        authority='read_only_geometry_not_source_measurement_or_edit_permission')
    value['evidence_sha256']=canonical_sha256(value)
    return value


def recipe_descriptor(recipe, parameters, *, yaw_deg=0, centre_xy=(0,0)):
    from twinpulse_core.model_recipe import compiled_parts,recipe_digest
    parts=compiled_parts(recipe,parameters)
    return describe(parts,[parameters[k] for k in ('width','depth','height')],
        parameters=recipe['parameters'],binding=dict(recipe_sha256=recipe_digest(recipe),
            actual_parameters=deepcopy(parameters)),yaw_deg=yaw_deg,centre_xy=centre_xy)
