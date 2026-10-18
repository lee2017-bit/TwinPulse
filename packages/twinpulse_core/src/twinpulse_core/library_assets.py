# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pinned static triangle meshes. No file loading, evaluation or CAD runtime.

Visual vertices are the inspected asset. The enclosing box is an explicitly
conservative static collider, never a replacement visual or SimReady claim.
"""
from dataclasses import dataclass
import json
import math
import re
from .revisions import canonical_sha256
from .models import SceneObject, ShapeSpec, Transform

VERSION='library-mesh-1.0'
MAX_VERTICES=12000
MAX_TRIANGLES=24000


@dataclass(frozen=True,slots=True)
class MeshAsset:
    logical_asset_id:str
    title:str
    source_name:str
    source_sha256:str
    origin:str
    license:str
    points:tuple[tuple[float,float,float],...]
    triangles:tuple[tuple[int,int,int],...]
    dimensions_m:tuple[float,float,float]

    def __post_init__(self):
        if (not isinstance(self.points,tuple) or not isinstance(self.triangles,tuple) or
            not isinstance(self.dimensions_m,tuple) or any(not isinstance(p,tuple) for p in self.points) or
            any(not isinstance(t,tuple) for t in self.triangles)):
            raise ValueError('LIBRARY_MESH_IMMUTABLE_TUPLES_REQUIRED')

    def body(self):
        return dict(schema_version=VERSION,logical_asset_id=self.logical_asset_id,title=self.title,
            source_name=self.source_name,source_sha256=self.source_sha256,origin=self.origin,license=self.license,
            units='m',up_axis='Z',local_origin='bounds_centre',points=[list(p) for p in self.points],
            triangles=[list(t) for t in self.triangles],dimensions_m=list(self.dimensions_m),
            physics_status='conservative_static_box_not_physics_validated')

    @property
    def version(self):return canonical_sha256(self.body())

    @property
    def asset_ref(self):return 'mesh_'+self.version[:24]

    def to_dict(self):return {**self.body(),'version':self.version,'asset_ref':self.asset_ref}

    @classmethod
    def from_dict(cls,value):
        fields={'schema_version','logical_asset_id','title','source_name','source_sha256','origin','license',
            'units','up_axis','local_origin','points','triangles','dimensions_m','physics_status','version','asset_ref'}
        if (not isinstance(value,dict) or set(value)!=fields or value['schema_version']!=VERSION or
            value['units']!='m' or value['up_axis']!='Z' or value['local_origin']!='bounds_centre' or
            value['physics_status']!='conservative_static_box_not_physics_validated'):
            raise ValueError('LIBRARY_MESH_CONTRACT_INVALID')
        for key in ('logical_asset_id','title','source_name','origin','license'):
            if not isinstance(value[key],str) or not 1<=len(value[key])<=300:raise ValueError('LIBRARY_MESH_METADATA_INVALID')
        if not re.fullmatch('[a-f0-9]{64}',value['source_sha256']):raise ValueError('LIBRARY_MESH_SOURCE_INVALID')
        points=value['points'];triangles=value['triangles'];size=value['dimensions_m']
        if (not isinstance(points,list) or not 4<=len(points)<=MAX_VERTICES or not isinstance(triangles,list)
            or not 1<=len(triangles)<=MAX_TRIANGLES or not isinstance(size,list) or len(size)!=3):
            raise ValueError('LIBRARY_MESH_CAPACITY_INVALID')
        numeric=lambda n:type(n) in (int,float) and math.isfinite(n)
        if any(not numeric(n) or not .001<=n<=20 for n in size):raise ValueError('LIBRARY_MESH_DIMENSIONS_INVALID')
        if any(not isinstance(p,list) or len(p)!=3 or any(not numeric(n) or abs(n)>20 for n in p) for p in points):
            raise ValueError('LIBRARY_MESH_POINTS_INVALID')
        if any(not isinstance(t,list) or len(t)!=3 or len(set(t))!=3 or
            any(type(n)!=int or not 0<=n<len(points) for n in t) for t in triangles):
            raise ValueError('LIBRARY_MESH_TOPOLOGY_INVALID')
        lower=[min(p[i] for p in points) for i in range(3)];upper=[max(p[i] for p in points) for i in range(3)]
        if any(abs(upper[i]-lower[i]-size[i])>1e-6 or abs(upper[i]+lower[i])>1e-6 for i in range(3)):
            raise ValueError('LIBRARY_MESH_BOUNDS_MISMATCH')
        if len(json.dumps(value,allow_nan=False).encode())>1500000:raise ValueError('LIBRARY_MESH_BYTE_LIMIT')
        result=cls(*(value[k] for k in ('logical_asset_id','title','source_name','source_sha256','origin','license')),
            tuple(tuple(p) for p in points),tuple(tuple(t) for t in triangles),tuple(size))
        if value['version']!=result.version or value['asset_ref']!=result.asset_ref:raise ValueError('LIBRARY_MESH_HASH_MISMATCH')
        return result


def normalize_mesh(points,triangles,*,logical_asset_id,title,source_name,source_sha256,origin,license,
                   metres_per_unit=1.,up_axis='Z'):
    if type(metres_per_unit) not in (float,int) or not math.isfinite(metres_per_unit) or metres_per_unit<=0:
        raise ValueError('LIBRARY_SOURCE_UNITS_REQUIRED')
    if up_axis not in {'Y','Z'}:raise ValueError('LIBRARY_SOURCE_AXIS_UNSUPPORTED')
    transformed=[]
    for p in points:
        if len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p):
            raise ValueError('LIBRARY_MESH_POINTS_INVALID')
        q=[v*metres_per_unit for v in p]
        transformed.append(q if up_axis=='Z' else [q[0],-q[2],q[1]])
    if not transformed:raise ValueError('LIBRARY_MESH_EMPTY')
    lo=[min(p[i] for p in transformed) for i in range(3)];hi=[max(p[i] for p in transformed) for i in range(3)]
    centre=[(a+b)/2 for a,b in zip(lo,hi)]
    mesh=MeshAsset(logical_asset_id,title,source_name,source_sha256,origin,license,
        tuple(tuple(p[i]-centre[i] for i in range(3)) for p in transformed),
        tuple(tuple(t) for t in triangles),tuple(hi[i]-lo[i] for i in range(3)))
    return MeshAsset.from_dict(mesh.to_dict())


def expand_library_asset(args):
    if not isinstance(args,dict) or set(args)!={'id','snapshot','position_m','yaw_deg'}:
        raise ValueError('LIBRARY_INSTANCE_CONTRACT_INVALID')
    if not isinstance(args['id'],str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,41}',args['id']):
        raise ValueError('LIBRARY_INSTANCE_ID_INVALID')
    asset=MeshAsset.from_dict(args['snapshot']);position=args['position_m'];yaw=args['yaw_deg']
    if (not isinstance(position,(tuple,list)) or len(position)!=3 or
        any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>20 for v in position) or
        type(yaw) not in (int,float) or not math.isfinite(yaw) or abs(yaw)>180):
        raise ValueError('LIBRARY_INSTANCE_POSE_INVALID')
    if abs(position[2]-asset.dimensions_m[2]/2)>.000001:raise ValueError('LIBRARY_INSTANCE_FLOOR_ONLY')
    return SceneObject(args['id'],'equipment',Transform(tuple(float(p) for p in position),(0.,0.,float(yaw))),
        ShapeSpec('box',asset.dimensions_m),asset_id=asset.asset_ref)


def edit_plan_version(plan,calls):
    """Never downcast pinned imports when editing an existing recipe/furniture."""
    required='2.3' if any(c.tool=='place_library_asset' for c in calls) else (
        '2.2' if any(c.tool in {'place_model_recipe','place_room_item'} or
            c.arguments.get('catalog_version')=='furniture-parametric-1.0' for c in calls) else
        '2.1' if any(c.tool=='place_furniture' for c in calls) else '2.0')
    return max(plan.plan_version,required)
