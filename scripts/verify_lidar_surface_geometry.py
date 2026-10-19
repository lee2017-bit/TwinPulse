# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary actual USD/recipe sections, not App or hardware acceptance."""
import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--usd-libs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    dll=os.add_dll_directory(str(a.usd_libs/'bin'));sys.path.insert(0,str(a.usd_libs))
    for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
    from pxr import Usd,UsdGeom,Gf,Vt
    from twinpulse_app.lidar_scene_geometry import scene_section,sensor_pose
    from twinpulse_core.room_visuals import display_meshes
    stage=Usd.Stage.CreateInMemory();robot=UsdGeom.Xform.Define(stage,'/World/TwinPulse/Fleet/Robot_test')
    robot.AddTranslateOp().Set((.4,.3,0));robot.AddRotateZOp().Set(90.)
    stage.DefinePrim(str(robot.GetPath())+'/Model','Xform').GetReferences().AddReference(str(ROOT/'assets/simulation/turtlebot3_burger/usd/turtlebot3_burger.usda'))
    pose,height,path=sensor_pose(stage,str(robot.GetPath()))
    assert abs(height-.182)<1e-8 and math.dist(pose[:2],[.4,.268])<1e-8 and abs(pose[2]-math.pi/2)<1e-8
    def cube(path,position,scale):
        prim=UsdGeom.Cube.Define(stage,path);prim.CreateSizeAttr(1);prim.AddTranslateOp().Set(Gf.Vec3d(*position));prim.AddScaleOp().Set(Gf.Vec3f(*scale));return prim
    cube('/World/TwinPulse/Environment/wall/geometry',(3,0,1.5),(.1,6,3))
    cube('/World/TwinPulse/Environment/desk/geometry',(1.5,0,.4),(1,.8,.8))
    group=UsdGeom.Xform.Define(stage,'/World/TwinPulse/Presentation/RoomModels/Item_desk')
    group.AddTranslateOp().Set((1.5,0,0));group.GetPrim().SetCustomDataByKey('currentGeometryIds',Vt.StringArray(['desk']))
    for part in display_meshes('desk',(1.,.8,.75)):
        mesh=UsdGeom.Mesh.Define(stage,str(group.GetPath())+'/'+part['name'])
        mesh.CreatePointsAttr([Gf.Vec3f(*v) for v in part['points']]);mesh.CreateFaceVertexCountsAttr([3]*len(part['faces']))
        mesh.CreateFaceVertexIndicesAttr([i for f in part['faces'] for i in f])
    start=time.perf_counter();index,geometry=scene_section(stage,height);build_s=time.perf_counter()-start
    center=index.cast((0,0),(1,0));leg=index.cast((0,-.32),(1,0))
    assert abs(center-2.95)<1e-6,center
    assert 1<leg<1.2,leg
    cube('/World/TwinPulse/Environment/solid/geometry',(.7,1,.2),(.2,.3,.4))
    low,_=scene_section(stage,height);assert abs(low.cast((0,1),(1,0))-.6)<1e-6
    upper,_=scene_section(stage,.6);assert abs(upper.cast((0,1),(1,0))-2.95)<1e-6
    samples=[]
    for _ in range(20):
        start=time.perf_counter();points=index.scan((0,0,0));samples.append(time.perf_counter()-start)
    result=dict(status='PASS',classification='SUPPLEMENTARY_ACTUAL_USD_NOT_USER_JOURNEY_OR_PHYSICAL',usd_version=Usd.GetVersion(),
        sensor=dict(world_pose=pose,height_m=height,frame_path=path),
        cases=dict(under_desk_hits_wall_m=center,desk_leg_hits_m=leg,low_solid_hits_m=.6,above_solid_hits_wall_m=2.95),
        geometry=geometry,build_s=build_s,scan_max_s=max(samples),hits=len(points),
        sources={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in ['packages/twinpulse_core/src/twinpulse_core/lidar_geometry.py',
            'packages/twinpulse_app/src/twinpulse_app/lidar_scene_geometry.py','assets/simulation/turtlebot3_burger/usd/payloads/base.usda']})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in {'geometry','sources'}}))


if __name__=='__main__':main()
