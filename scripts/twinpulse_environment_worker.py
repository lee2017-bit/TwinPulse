# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Existing OpenUSD -> finite static environment; never starts Kit or writes input."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

# Keep standalone invocations read-only to the verified source directory too.
sys.dont_write_bytecode=True
from twinpulse_library_worker import load_existing_usd


def inspect_environment(path,unit):
    load_existing_usd()
    from pxr import Usd,UsdGeom,UsdShade,Gf,Sdf
    layer=Sdf.Layer.FindOrOpen(str(path))
    if layer is None:raise ValueError('ENVIRONMENT_SOURCE_OPEN_FAILED')
    if layer.subLayerPaths or layer.GetExternalReferences() or layer.GetExternalAssetDependencies():
        raise ValueError('ENVIRONMENT_EXTERNAL_DEPENDENCIES_UNSUPPORTED')
    stage=Usd.Stage.Open(layer,load=Usd.Stage.LoadNone)
    if not stage or not stage.HasAuthoredMetadata('upAxis'):raise ValueError('ENVIRONMENT_AXIS_REQUIRED')
    axis=str(UsdGeom.GetStageUpAxis(stage))
    if axis not in {'Y','Z'}:raise ValueError('ENVIRONMENT_AXIS_UNSUPPORTED')
    authored=float(UsdGeom.GetStageMetersPerUnit(stage)) if stage.HasAuthoredMetadata('metersPerUnit') else None
    scale={'m':1.,'cm':.01,'mm':.001}.get(unit,authored)
    if scale not in {1.,.01,.001}:raise ValueError('ENVIRONMENT_SELECT_UNITS')
    meshes=[];cache=UsdGeom.XformCache(Usd.TimeCode.Default());nv=nt=0
    for prim in stage.Traverse():
        if prim.HasAuthoredReferences() or prim.HasAuthoredPayloads() or prim.IsInstance():
            raise ValueError('ENVIRONMENT_COMPOSITION_UNSUPPORTED')
        for attr in prim.GetAttributes():
            if attr.GetNumTimeSamples():raise ValueError('ENVIRONMENT_STATIC_ONLY')
            if attr.GetTypeName() in {Sdf.ValueTypeNames.Asset,Sdf.ValueTypeNames.AssetArray} and attr.Get():
                raise ValueError('ENVIRONMENT_EXTERNAL_ASSET_UNSUPPORTED')
        if not prim.IsA(UsdGeom.Mesh):
            if prim.IsA(UsdGeom.Gprim):raise ValueError('ENVIRONMENT_TRIANGULAR_MESH_ONLY')
            continue
        mesh=UsdGeom.Mesh(prim)
        if mesh.ComputeVisibility()=='invisible':continue
        if (mesh.ComputePurpose() not in {'default','render'} or mesh.GetHoleIndicesAttr().Get() or
                mesh.GetSubdivisionSchemeAttr().Get() not in {None,'none'}):raise ValueError('ENVIRONMENT_MESH_POLICY_UNSUPPORTED')
        points=mesh.GetPointsAttr().Get();counts=list(mesh.GetFaceVertexCountsAttr().Get() or [])
        indices=list(mesh.GetFaceVertexIndicesAttr().Get() or [])
        if points is None or not counts or any(n!=3 for n in counts) or len(indices)!=3*len(counts):
            raise ValueError('ENVIRONMENT_TRIANGULATION_REQUIRED')
        if any(not 0<=i<len(points) for i in indices):raise ValueError('ENVIRONMENT_INDEX_INVALID')
        transform=cache.GetLocalToWorldTransform(prim)
        world=[list(transform.Transform(Gf.Vec3d(*p))) for p in points]
        world=[[p[0]*scale,-p[2]*scale,p[1]*scale] if axis=='Y' else [v*scale for v in p] for p in world]
        if any(not math.isfinite(v) for p in world for v in p):raise ValueError('ENVIRONMENT_NONFINITE')
        color=[.65,.65,.65]
        display=mesh.GetDisplayColorAttr().Get()
        if display:color=list(display[0])
        else:
            material,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            if material:
                surface=material.ComputeSurfaceSource()[0]
                if surface:
                    diffuse=surface.GetInput('diffuseColor').Get()
                    if diffuse is not None:color=list(diffuse)
        path_text=str(prim.GetPath());name=prim.GetName()
        category=''.join(c for c in name if not c.isdigit()).lower()
        if category not in {'floor','wall','door','window','chair','table','sofa','storage','refrigerator'}:category='unknown'
        triangles=[indices[i:i+3] for i in range(0,len(indices),3)]
        determinant=transform.GetDeterminant()
        if (mesh.GetOrientationAttr().Get()=='leftHanded') != (determinant<0):
            triangles=[[t[0],t[2],t[1]] for t in triangles]
        meshes.append(dict(id='Env_'+hashlib.sha256(path_text.encode()).hexdigest()[:20],source_path=path_text,
            category=category,label=name,points_m=world,triangles=triangles,color_rgb=[float(c) for c in color],translation_m=[0.,0.,0.]))
        nv+=len(world);nt+=len(triangles)
        if len(meshes)>128 or nv>12000 or nt>24000:raise ValueError('ENVIRONMENT_GEOMETRY_BUDGET')
    floors=[p[2] for m in meshes if m['category']=='floor' for p in m['points_m']]
    if not floors:raise ValueError('ENVIRONMENT_FLOOR_REQUIRED')
    floor_offset=-max(floors)
    for m in meshes:
        for p in m['points_m']:p[2]+=floor_offset
    return dict(schema_version='environment-static-1.0',source_name=path.name,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_up_axis=axis,
        source_meters_per_unit=authored,meters_per_unit=scale,
        units_basis='authored' if unit is None else 'selected_for_sim',floor_offset_m=floor_offset,meshes=meshes)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--units',choices=['m','cm','mm'])
    args=parser.parse_args()
    result=inspect_environment(args.input,args.units)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,allow_nan=False)
