# SPDX-License-Identifier: Apache-2.0
"""Read-only triangle/height intersections for imported-space review.

Not AABB colliders, not a navigation map and never a robot permission. A surface
outside this plane is unobserved, not free. Source units remain uncalibrated.
"""
import math
from .environment_source import checked_environment,mesh_points
from .revisions import canonical_sha256


def horizontal_section(environment,height_m):
    env=checked_environment(environment)
    if type(height_m) not in (int,float) or not math.isfinite(height_m) or not 0.<height_m<=3.:
        raise ValueError('SECTION_HEIGHT_INVALID')
    segments=[];seen=set();coplanar=0
    for mesh in env['meshes']:
        points=mesh_points(mesh)
        for triangle in mesh['triangles']:
            vertices=[points[i] for i in triangle];signed=[p[2]-height_m for p in vertices]
            if all(abs(d)<1e-8 for d in signed):
                coplanar+=1;continue  # A coincident face is not a unique return line.
            intersections=[]
            for i,j in ((0,1),(1,2),(2,0)):
                a,b=vertices[i],vertices[j];da,db=signed[i],signed[j]
                if abs(da)<1e-8:intersections.append(a[:2])
                if da*db<0.:
                    t=da/(da-db);intersections.append([a[k]+t*(b[k]-a[k]) for k in range(2)])
            unique={tuple(round(v,9) for v in p):p for p in intersections}
            if len(unique)!=2:continue
            ends=list(unique.values())
            if math.dist(*ends)<1e-7:continue
            key=(mesh['id'],tuple(sorted(unique)))
            if key in seen:continue
            seen.add(key);segments.append(dict(object_id=mesh['id'],source_path=mesh['source_path'],
                category=mesh['category'],ends_m=ends))
    return dict(schema='environment-height-section-1.0',source_sha256=env['source_sha256'],
        environment_sha256=canonical_sha256(env),height_m=height_m,units_basis=env['units_basis'],
        segments=segments,coplanar_triangles_omitted=coplanar,world_registration_verified=False,
        scope='REVIEW_ONLY_UNCALIBRATED_HEIGHT_SECTION_NOT_FREE_SPACE_OR_CONTROL')


def matching_outline(environment,height_m):
    """Adapter for the existing bounded offline RoomMatcher, not box proxies."""
    env=checked_environment(environment);section=horizontal_section(env,height_m)
    # Windows/glass may not return a beam. Retain them in section inventory but
    # do not use them as positive localization surfaces. Unknown isn't free.
    segments=[s['ends_m'] for s in section['segments'] if s['category'] in
        {'wall','door','chair','table','sofa','storage','refrigerator'}]
    if not 4<=len(segments)<=1024:raise ValueError('SECTION_MATCH_SEGMENT_BUDGET')
    floor=[p for mesh in env['meshes'] if mesh['category']=='floor' for p in mesh_points(mesh)]
    bounds=[min(p[0] for p in floor),max(p[0] for p in floor),min(p[1] for p in floor),max(p[1] for p in floor)]
    if max(bounds[1]-bounds[0],bounds[3]-bounds[2])>15.:raise ValueError('SECTION_MATCH_EXTENT_BUDGET')
    return dict(bounds_m=bounds,segments=segments,solids=[],revision=canonical_sha256(section),
        geometry_status='IMPORTED_TRIANGLE_SECTION_NOT_CALIBRATED',
        limits=['Floor bounds are a search box, not free-space permission.',
            'No first-hit/occlusion validation, physical surface reflectivity or as-built calibration.'])
