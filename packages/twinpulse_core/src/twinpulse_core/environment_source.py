# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Bounded static-space geometry. Bounds are metadata, never room colliders."""
from copy import deepcopy
import math
import re
from .models import SceneObject, ShapeSpec, Transform
from .revisions import canonical_sha256

SCHEMA = 'environment-static-1.0'
MOVABLE = {'chair','table','sofa','storage','refrigerator'}


def _numbers(value, length, limit=100.):
    return (isinstance(value,(list,tuple)) and len(value)==length and
            all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=limit for x in value))


def checked_environment(value):
    fields={'schema_version','source_name','source_sha256','source_up_axis','source_meters_per_unit',
            'meters_per_unit','units_basis','floor_offset_m','meshes'}
    from .environment_overlays import SCHEMA as HYBRID,checked_overlay,checked_overlay_floor
    hybrid=isinstance(value,dict) and value.get('schema_version')==HYBRID
    if not isinstance(value,dict) or set(value)!=fields|({'overlays'} if hybrid else set()) or value['schema_version'] not in {SCHEMA,HYBRID}:
        raise ValueError('ENVIRONMENT_CONTRACT_INVALID')
    if (not isinstance(value['source_name'],str) or not 1<=len(value['source_name'])<=240 or
            any(c in value['source_name'] for c in '/\\\0') or
            not isinstance(value['source_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',value['source_sha256'])):
        raise ValueError('ENVIRONMENT_SOURCE_INVALID')
    if (value['source_up_axis'] not in {'Y','Z'} or
            type(value['meters_per_unit']) not in (int,float) or value['meters_per_unit'] not in {1.,.01,.001} or
            value['units_basis'] not in {'authored','selected_for_sim'} or
            not _numbers([value['floor_offset_m']],1)):
        raise ValueError('ENVIRONMENT_UNITS_INVALID')
    authored=value['source_meters_per_unit']
    if authored is not None and (type(authored) not in (int,float) or not math.isfinite(authored) or authored<=0):
        raise ValueError('ENVIRONMENT_AUTHORED_UNITS_INVALID')
    if value['units_basis']=='authored' and authored!=value['meters_per_unit']:
        raise ValueError('ENVIRONMENT_UNITS_PROVENANCE_INVALID')
    meshes=value['meshes']
    if not isinstance(meshes,list) or not 1<=len(meshes)<=128:raise ValueError('ENVIRONMENT_MESH_BUDGET')
    ids=set();paths=set();vertices=faces=0
    for mesh in meshes:
        if not isinstance(mesh,dict) or set(mesh)!={'id','source_path','category','label','points_m','triangles','color_rgb','translation_m'}:
            raise ValueError('ENVIRONMENT_MESH_INVALID')
        if (not isinstance(mesh['id'],str) or not re.fullmatch('Env_[a-f0-9]{20}',mesh['id']) or mesh['id'] in ids or
                not isinstance(mesh['source_path'],str) or not mesh['source_path'].startswith('/') or
                len(mesh['source_path'])>512 or mesh['source_path'] in paths):raise ValueError('ENVIRONMENT_MESH_ID_INVALID')
        ids.add(mesh['id']);paths.add(mesh['source_path'])
        if (mesh['category'] not in MOVABLE|{'floor','wall','door','window','unknown'} or
                not isinstance(mesh['label'],str) or not 1<=len(mesh['label'])<=120 or
                not _numbers(mesh['translation_m'],3,2.) or mesh['translation_m'][2]!=0 or
                mesh['category'] not in MOVABLE and any(mesh['translation_m'])):
            raise ValueError('ENVIRONMENT_OBJECT_INVALID')
        if not _numbers(mesh['color_rgb'],3,1.) or min(mesh['color_rgb'])<0:raise ValueError('ENVIRONMENT_COLOR_INVALID')
        points=mesh['points_m'];triangles=mesh['triangles']
        if (not isinstance(points,list) or len(points)<3 or any(not _numbers(p,3) for p in points) or
                not isinstance(triangles,list) or not triangles):raise ValueError('ENVIRONMENT_TOPOLOGY_INVALID')
        for t in triangles:
            if (not isinstance(t,list) or len(t)!=3 or len(set(t))!=3 or
                    any(type(i) is not int or not 0<=i<len(points) for i in t)):raise ValueError('ENVIRONMENT_INDEX_INVALID')
        vertices+=len(points);faces+=len(triangles)
    if vertices>12000 or faces>24000:raise ValueError('ENVIRONMENT_GEOMETRY_BUDGET')
    if not any(m['category']=='floor' for m in meshes):raise ValueError('ENVIRONMENT_FLOOR_REQUIRED')
    if hybrid:
        if not isinstance(value['overlays'],list) or len(value['overlays'])>32:raise ValueError('ENVIRONMENT_OVERLAY_BUDGET')
        added=set()
        for overlay in value['overlays']:
            overlay=checked_overlay(overlay);identity=overlay['item']['id']
            if identity in added:raise ValueError('ENVIRONMENT_OVERLAY_DUPLICATE')
            added.add(identity);checked_overlay_floor(overlay,meshes)
    return deepcopy(value)


def mesh_points(mesh):
    return [[p[i]+mesh['translation_m'][i] for i in range(3)] for p in mesh['points_m']]


def object_bounds(mesh):
    points=mesh_points(mesh)
    return ([min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)])


def environment_objects(value):
    """Metadata proxies only; the compiler authors the actual mesh instead."""
    result=[]
    for mesh in value['meshes']:
        lo,hi=object_bounds(mesh)
        kind=mesh['category'] if mesh['category'] in {'floor','wall'} else 'equipment'
        result.append(SceneObject(mesh['id'],kind,Transform(tuple((a+b)/2 for a,b in zip(lo,hi)),(0.,0.,0.)),
            ShapeSpec('box',tuple(float(max(b-a,.000001)) for a,b in zip(lo,hi))),collision=False))
    from .environment_overlays import overlay_objects
    return tuple(result)+tuple(obj for overlay in value.get('overlays',[]) for obj in overlay_objects(overlay))


def checked_environment_change(before,after):
    before=checked_environment(before);after=checked_environment(after)
    from .environment_overlays import overlay_objects
    base=deepcopy(before);next_base=deepcopy(after);changed=[]
    old_overlays={o['item']['id']:o for o in base.pop('overlays',[])}
    new_overlays={o['item']['id']:o for o in next_base.pop('overlays',[])}
    base['schema_version']=next_base['schema_version']=SCHEMA
    for old,new in zip(base['meshes'],next_base['meshes']):
        if old['translation_m']!=new['translation_m']:changed.append(old['id'])
        old['translation_m']=new['translation_m']=[0.,0.,0.]
    overlay_changes=[key for key in old_overlays.keys()|new_overlays.keys() if old_overlays.get(key)!=new_overlays.get(key)]
    if canonical_sha256(base)!=canonical_sha256(next_base) or len(changed)+len(overlay_changes)!=1:
        raise ValueError('ENVIRONMENT_EDIT_ONLY_ONE_FURNITURE_TRANSLATION')
    if overlay_changes:
        identity=overlay_changes[0];old=old_overlays.get(identity);new=new_overlays.get(identity)
        if old and new:
            # Existing estimates may only translate in the floor plane. Evidence,
            # size, kind and uncertainty cannot be silently rewritten by a move.
            a,b=deepcopy(old),deepcopy(new)
            for index in (0,1):a['item']['position_m'][index]=b['item']['position_m'][index]=0.
            if a!=b:raise ValueError('ENVIRONMENT_OVERLAY_MOVE_ONLY')
        return {obj.id for value in (old,new) if value for obj in overlay_objects(value)}
    return set(changed)


def move_environment(value,identity,translation):
    result=checked_environment(value)
    if not _numbers(translation,3,2.) or translation[2]!=0:raise ValueError('ENVIRONMENT_TRANSLATION_INVALID')
    overlay=next((o for o in result.get('overlays',[]) if o['item']['id']==identity),None)
    if overlay:
        overlay['item']['position_m']=[overlay['item']['position_m'][i]+translation[i] for i in range(3)]
        result=checked_environment(result);checked_environment_change(value,result)
        return result
    target=next((m for m in result['meshes'] if m['id']==identity),None)
    if target is None or target['category'] not in MOVABLE:raise ValueError('ENVIRONMENT_OBJECT_READ_ONLY')
    target['translation_m']=[target['translation_m'][i]+translation[i] for i in range(3)]
    result=checked_environment(result);checked_environment_change(value,result)
    return result
