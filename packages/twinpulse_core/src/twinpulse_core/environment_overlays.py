# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Estimated room props layered over an immutable scanned-space source.

No camera pose or metric registration is inferred. The uncertainty envelope is
an explicit synthetic navigation/physics keepout, never a LiDAR return.
"""
from copy import deepcopy
import math
import re

from .models import SceneObject, ShapeSpec, Transform
from .room_items import checked_room_item, expand_room_item, room_item_risk

SCHEMA = 'environment-static-1.1'
KINDS = ('floor_fan','basket','bag','box','clothing_pile','cable_bundle',
         'power_adapter','power_strip','small_equipment','unknown')


def checked_overlay(value):
    if not isinstance(value,dict) or set(value)!={'item','uncertainty_m','evidence'}:
        raise ValueError('ENVIRONMENT_OVERLAY_INVALID')
    item=checked_room_item(value['item'])
    if not re.fullmatch('Added_[a-f0-9]{20}',item['id']) or item['kind'] not in KINDS:
        raise ValueError('ENVIRONMENT_OVERLAY_KIND_OR_ID_INVALID')
    if (any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100 for v in item['position_m']) or
            any(v>3 for v in item['dimensions_m']) or
            abs(item['position_m'][2]-item['dimensions_m'][2]/2)>1e-6):
        raise ValueError('ENVIRONMENT_OVERLAY_FLOOR_PROP_REQUIRED')
    margin=value['uncertainty_m']
    if type(margin) not in (int,float) or not math.isfinite(margin) or not .05<=margin<=1.:
        raise ValueError('ENVIRONMENT_OVERLAY_UNCERTAINTY_INVALID')
    evidence=value['evidence']
    if (not isinstance(evidence,dict) or set(evidence)!={'basis','source_name','sha256','alignment_verified'} or
            evidence['alignment_verified'] is not False or evidence['basis'] not in {'manual_estimate','photo_estimate','lidar_estimate'}):
        raise ValueError('ENVIRONMENT_OVERLAY_EVIDENCE_INVALID')
    if evidence['basis']=='manual_estimate':
        if evidence['source_name'] is not None or evidence['sha256'] is not None:
            raise ValueError('ENVIRONMENT_OVERLAY_EVIDENCE_INVALID')
    elif (not isinstance(evidence['source_name'],str) or not 1<=len(evidence['source_name'])<=180 or
          any(c in evidence['source_name'] for c in '/\\\0\r\n') or
          not isinstance(evidence['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',evidence['sha256'])):
        raise ValueError('ENVIRONMENT_OVERLAY_EVIDENCE_INVALID')
    return deepcopy(value)


def overlay_objects(overlay):
    overlay=checked_overlay(overlay);item=overlay['item']
    # Reuse exactly the versioned photo-room catalog, including entanglement.
    parts=expand_room_item(item)
    sx,sy,_=item['dimensions_m'];x,y,_=item['position_m']
    margin=overlay['uncertainty_m']+(.10 if room_item_risk(item) in {'entanglement','unknown'} else 0.)
    envelope=SceneObject(item['id']+'_uncertainty','equipment',
        Transform((float(x),float(y),.175),(0.,0.,float(item['yaw_deg']))),
        ShapeSpec('box',(float(sx+2*margin),float(sy+2*margin),.35)))
    return parts+(envelope,)


def footprint(obj):
    x,y,z=obj.transform.position_m;sx,sy,sz=obj.shape.dimensions_m
    c=math.cos(math.radians(obj.transform.rotation_rpy_deg[2]));s=math.sin(math.radians(obj.transform.rotation_rpy_deg[2]))
    return [[x+a*c-b*s,y+a*s+b*c,z] for a,b in ((-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2))]


def checked_overlay_floor(overlay,meshes):
    """Require the whole uncertainty footprint on actual flat floor triangles.

    Testing the room bounding box alone would bridge holes and concave corners.
    Overlapping/ambiguous floor coverage is rejected rather than guessed free.
    """
    from .environment_navigation import clip,area,convex_overlap_area
    envelope=overlay_objects(overlay)[-1]
    x,y,_=envelope.transform.position_m;sx,sy,_=envelope.shape.dimensions_m
    angle=math.radians(envelope.transform.rotation_rpy_deg[2]);c,s=math.cos(angle),math.sin(angle)
    coverage=0.;pieces=[]
    for mesh in meshes:
        if mesh['category']!='floor':continue
        points=[[p[i]+mesh['translation_m'][i] for i in range(3)] for p in mesh['points_m']]
        for triangle in mesh['triangles']:
            vertices=[points[i] for i in triangle]
            if max(abs(p[2]) for p in vertices)>1e-4:continue
            poly=[[(p[0]-x)*c+(p[1]-y)*s,-(p[0]-x)*s+(p[1]-y)*c,0.] for p in vertices]
            for axis,bound,positive in ((0,-sx/2,True),(0,sx/2,False),(1,-sy/2,True),(1,sy/2,False)):
                poly=clip(poly,axis,bound,positive)
            if area(poly)>1e-12:
                if len(pieces)>=512:raise ValueError('ENVIRONMENT_OVERLAY_FLOOR_BUDGET')
                if any(convex_overlap_area(poly,p)>1e-10 for p in pieces):raise ValueError('ENVIRONMENT_OVERLAY_FLOOR_AMBIGUOUS')
                pieces.append(poly);coverage+=area(poly)
    if abs(coverage-sx*sy)>1e-6:raise ValueError('ENVIRONMENT_OVERLAY_OUTSIDE_FLOOR')


def overlay_meshes(environment):
    """Deterministic box meshes. Synthetic keepouts remain separately flagged."""
    result=[]
    faces=[[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
           [2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]]
    for overlay in environment.get('overlays',[]):
        for obj in overlay_objects(overlay):
            x,y,z=obj.transform.position_m;sx,sy,sz=obj.shape.dimensions_m
            c=math.cos(math.radians(obj.transform.rotation_rpy_deg[2]));s=math.sin(math.radians(obj.transform.rotation_rpy_deg[2]))
            points=[[x+a*c-b*s,y+a*s+b*c,z+d] for d in (-sz/2,sz/2) for b in (-sy/2,sy/2) for a in (-sx/2,sx/2)]
            synthetic=obj.id.endswith(('_keepout','_uncertainty'))
            result.append(dict(id=obj.id,source_path='/Estimated/'+overlay['item']['id'],category='added_obstacle',
                label=overlay['item']['label'],points_m=points,triangles=faces,color_rgb=[.84,.48,.16],translation_m=[0.,0.,0.],
                collision=obj.collision,synthetic_keepout=synthetic,evidence=overlay['evidence']))
    return result


def overlay_keepout_polygons(environment):
    # Filled footprint, not just box surface triangles: a tall box's interior
    # must not be erroneously free between its vertical sides at robot height.
    return [footprint(overlay_objects(o)[-1]) for o in environment.get('overlays',[])]


def add_overlay(environment,overlay):
    from .environment_source import checked_environment,checked_environment_change
    result=checked_environment(environment);overlay=checked_overlay(overlay)
    result['schema_version']=SCHEMA;result.setdefault('overlays',[]).append(overlay)
    result=checked_environment(result);checked_environment_change(environment,result)
    return result


def remove_overlay(environment,identity):
    from .environment_source import checked_environment,checked_environment_change
    result=checked_environment(environment)
    if not any(o['item']['id']==identity for o in result.get('overlays',[])):
        raise ValueError('ENVIRONMENT_OVERLAY_NOT_FOUND')
    result['overlays']=[o for o in result['overlays'] if o['item']['id']!=identity]
    result=checked_environment(result);checked_environment_change(environment,result)
    return result
