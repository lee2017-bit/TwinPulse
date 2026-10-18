# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Finite bundled Library worker / trusted example MCP stdio server.

Never runs model-generated code. USD is inspected in the existing Isaac Python
environment, not imported into the desktop interpreter or live stage.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))

_dll_handles=[]


def load_existing_usd():
    """Use only this Isaac interpreter's installed USD, without starting Kit.

    Isaac python.bat does not itself enable omni.usd.libs. This process-local
    path setup neither installs USD nor modifies the user's Python/PATH.
    """
    import importlib.util
    if importlib.util.find_spec('pxr') is not None:return
    isaac=Path(sys.executable).resolve().parents[2]
    candidates=[p for p in (isaac/'extscache').glob('omni.usd.libs-*')
        if ('cp'+str(sys.version_info.major)+str(sys.version_info.minor)) in p.name
        and (p/'pxr'/'Usd'/'_usd.pyd').is_file()]
    if len(candidates)!=1:raise ValueError('EXISTING_ISAAC_USD_RUNTIME_NOT_UNIQUE_OR_AVAILABLE')
    usd=candidates[0]
    for folder in (usd/'bin',isaac/'kit',isaac/'kit'/'kernel',isaac/'kit'/'plugins'):
        if folder.is_dir() and hasattr(os,'add_dll_directory'):_dll_handles.append(os.add_dll_directory(str(folder)))
    sys.path.insert(0,str(usd))


def inspect_usd(path):
    load_existing_usd()
    from pxr import Gf,Sdf,Usd,UsdGeom
    layer=Sdf.Layer.FindOrOpen(str(path))
    if layer is None or layer.subLayerPaths or layer.GetExternalReferences():
        raise ValueError('USD_EXTERNAL_DEPENDENCIES_UNSUPPORTED')
    stage=Usd.Stage.Open(layer,load=Usd.Stage.LoadNone)
    if stage is None:raise ValueError('USD_STAGE_INVALID')
    if not stage.HasAuthoredMetadata('metersPerUnit') or not stage.HasAuthoredMetadata('upAxis'):
        raise ValueError('USD_EXPLICIT_UNITS_AND_AXIS_REQUIRED')
    points=[];triangles=[]
    cache=UsdGeom.XformCache(Usd.TimeCode.Default())
    for prim in stage.Traverse():
        if prim.HasAuthoredReferences() or prim.HasAuthoredPayloads() or prim.IsInstance():
            raise ValueError('USD_COMPOSITION_UNSUPPORTED')
        if prim.GetTypeName() in {'SkelRoot','Skeleton','NurbsCurves','NurbsPatch','PointInstancer'}:
            raise ValueError('USD_STATIC_TRIANGLE_MESH_ONLY')
        for attr in prim.GetAttributes():
            if attr.GetNumTimeSamples():raise ValueError('USD_ANIMATION_UNSUPPORTED')
            if attr.GetTypeName() in {Sdf.ValueTypeNames.Asset,Sdf.ValueTypeNames.AssetArray} and attr.Get():
                raise ValueError('USD_EXTERNAL_ASSET_UNSUPPORTED')
        if not prim.IsA(UsdGeom.Mesh):
            if prim.IsA(UsdGeom.Imageable) and UsdGeom.Imageable(prim).ComputeVisibility()!='invisible' and (
                    prim.IsA(UsdGeom.Gprim) or prim.GetTypeName() not in {'Xform','Scope','Camera'}):
                raise ValueError('USD_VISIBLE_GEOMETRY_REQUIRES_MESH_TESSELLATION: '+str(prim.GetPath()))
            continue
        mesh=UsdGeom.Mesh(prim)
        if mesh.ComputeVisibility()=='invisible':continue
        if mesh.ComputePurpose() not in {'default','render'}:raise ValueError('USD_MESH_PURPOSE_UNSUPPORTED')
        if mesh.GetSubdivisionSchemeAttr().Get() not in {None,'none'}:
            raise ValueError('USD_SUBDIVISION_REQUIRES_TESSELLATION')
        if mesh.GetHoleIndicesAttr().Get():raise ValueError('USD_HOLES_REQUIRE_TESSELLATION')
        local=mesh.GetPointsAttr().Get();counts=mesh.GetFaceVertexCountsAttr().Get();indices=mesh.GetFaceVertexIndicesAttr().Get()
        if local is None or counts is None or indices is None or sum(counts)!=len(indices):
            raise ValueError('USD_MESH_TOPOLOGY_INVALID')
        transform=cache.GetLocalToWorldTransform(prim);offset=len(points)
        points.extend(list(transform.Transform(Gf.Vec3d(*p))) for p in local)
        if len(points)>12000:raise ValueError('USD_VERTEX_LIMIT')
        cursor=0;left=mesh.GetOrientationAttr().Get()=='leftHanded'
        for count in counts:
            if count!=3:raise ValueError('USD_TRIANGULATION_REQUIRED')
            face=list(indices[cursor:cursor+count]);cursor+=count
            if any(not 0<=n<len(local) for n in face):raise ValueError('USD_INDEX_INVALID')
            t=[offset+n for n in face]
            triangles.append([t[0],t[2],t[1]] if left else t)
            if len(triangles)>24000:raise ValueError('USD_TRIANGLE_LIMIT')
    return dict(points=points,triangles=triangles,metres_per_unit=UsdGeom.GetStageMetersPerUnit(stage),
        up_axis=str(UsdGeom.GetStageUpAxis(stage)),inspector='existing_OpenUSD_static_mesh_inspector')


def mcp_server():
    from twinpulse_app.library_tools import csv_summary,CSV_SCHEMA
    initialized=False;ready=False
    for line in sys.stdin:
        if len(line)>8*1024*1024:raise ValueError('MCP_INPUT_BYTE_LIMIT')
        message=json.loads(line);identity=message.get('id');method=message.get('method');params=message.get('params',{})
        if method=='notifications/initialized':ready=initialized;continue
        try:
            if message.get('jsonrpc')!='2.0':raise ValueError('JSON_RPC_VERSION_INVALID')
            if method=='initialize':
                if params.get('protocolVersion')!='2025-11-25':raise ValueError('MCP_PROTOCOL_UNSUPPORTED')
                initialized=True;result=dict(protocolVersion='2025-11-25',capabilities=dict(tools={}),
                    serverInfo=dict(name='twinpulse-csv-analysis',version='1.0.0'))
            elif not ready:raise ValueError('MCP_NOT_INITIALIZED')
            elif method=='tools/list':
                result=dict(tools=[dict(name='csv.summary',title='CSV numeric summary',inputSchema={**CSV_SCHEMA,
                    'properties':{**CSV_SCHEMA['properties'],'bytes_base64':dict(type='string')},
                    'required':['column','bytes_base64']})])
            elif method=='tools/call' and params.get('name')=='csv.summary':
                args=dict(params['arguments']);raw=base64.b64decode(args.pop('bytes_base64'),validate=True)
                output=csv_summary(raw,args)
                result=dict(content=[dict(type='text',text=json.dumps(output))],structuredContent=output,isError=False)
            elif method=='ping':result={}
            else:raise ValueError('MCP_METHOD_UNSUPPORTED')
            response=dict(jsonrpc='2.0',id=identity,result=result)
        except (ValueError,KeyError,TypeError) as error:
            response=dict(jsonrpc='2.0',id=identity,error=dict(code=-32602,message=str(error)[:200]))
        if identity is not None:print(json.dumps(response,separators=(',',':')),flush=True)
    return 0


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mcp',action='store_true')
    parser.add_argument('--probe-usd',action='store_true')
    parser.add_argument('--usd-input',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.probe_usd:
        if args.mcp or args.usd_input or args.output:raise ValueError('WORKER_ARGUMENT_CONFLICT')
        load_existing_usd()
        from pxr import Usd
        print(json.dumps(dict(usd_version=list(Usd.GetVersion()),kit_started=False)))
        return 0
    if args.mcp:
        if args.usd_input or args.output:raise ValueError('WORKER_ARGUMENT_CONFLICT')
        return mcp_server()
    if not args.usd_input or not args.output:raise ValueError('WORKER_INPUT_REQUIRED')
    result=inspect_usd(args.usd_input.resolve())
    # A unique owned job output, never an arbitrary existing user file.
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,allow_nan=False)
    return 0


if __name__=='__main__':raise SystemExit(main())
