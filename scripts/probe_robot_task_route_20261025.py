# SPDX-License-Identifier: Apache-2.0
"""Read-only original-goal replay on a separately authored OpenUSD stage."""
import hashlib,importlib.util,json,math,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from twinpulse_library_worker import load_existing_usd
load_existing_usd()
from pxr import Usd,UsdGeom
from twinpulse_core.environment_navigation import navigation_cells
from twinpulse_core.navigation_grid import encode_navigation_grid
from twinpulse_core.robot_survey import route_to
from twinpulse_app.lidar_scene_geometry import mesh_triangles
spec=importlib.util.spec_from_file_location('task_route_author',ROOT/'extensions/twinpulse.extension/twinpulse/extension/environment_geometry.py')
author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
out=ROOT/'outputs/robot-task-20261025-01/route-replay01';out.mkdir(exist_ok=False)
source=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvmcf9wa_18f1e6d1/project.scene-edit-transaction.json'
raw=source.read_bytes();transaction=json.loads(raw)
env=transaction['operation']['tool_call']['arguments']['environment']
stage=Usd.Stage.CreateInMemory();UsdGeom.Xform.Define(stage,'/World/TwinPulse');UsdGeom.Xform.Define(stage,author.ROOT);author.author_environment(stage,env)
meshes=[]
for obj in stage.GetPrimAtPath(author.ROOT).GetChildren():
    triangles=mesh_triangles(stage.GetPrimAtPath(str(obj.GetPath())+'/geometry'))
    meshes.append(dict(id=obj.GetName(),category=obj.GetCustomDataByKey('environmentCategory'),label=obj.GetCustomDataByKey('environmentLabel'),
        points_m=[list(p) for t in triangles for p in t],triangles=[[i,i+1,i+2] for i in range(0,len(triangles)*3,3)],synthetic_keepout=bool(obj.GetCustomDataByKey('syntheticKeepout'))))
nav=navigation_cells(meshes);cells=nav['cells'];geometry={k:nav[k] for k in ('bounds','obstacles')}
known={tuple(math.floor(v/.1) for v in r[:2]):r[2] for r in cells}
def blocked(point):
    x,y=point;result=[]
    for ix in range(math.floor((x-.30)/.1),math.floor((x+.30)/.1)+1):
        for iy in range(math.floor((y-.30)/.1),math.floor((y+.30)/.1)+1):
            dx=max(ix*.1-x,0.,x-(ix+1)*.1);dy=max(iy*.1-y,0.,y-(iy+1)*.1)
            if math.hypot(dx,dy)<=.30 and known.get((ix,iy))!='free':result.append(dict(cell=[ix,iy],state=known.get((ix,iy),'unknown'),distance=math.hypot(dx,dy)))
    return result
failed=json.loads((ROOT/'outputs/robot-task-20261025-01/survey04/result.json').read_bytes())
job=failed['final_task'];goal=job['coverage']['goal'];rows=[]
for event in job['events']:
    if event['kind'] not in {'child_completed','observation'}:continue
    pose=event['pose']['position_m']
    try:route=route_to(pose,goal,geometry,observed_cells=cells);error=None
    except ValueError as exc:route=None;error=str(exc)
    rows.append(dict(kind=event['kind'],at_ms=event['at_ms'],pose=pose,route=route,error=error,blocked=blocked(pose[:2])))
value=dict(scope='SEPARATE_OPENUSD_SAVED_SCENE_REPLAY_NOT_ORIGINAL_LIVE_MAP_CAPTURE',source_sha256=hashlib.sha256(raw).hexdigest(),scene_revision=transaction['operation']['result_revision'] if 'result_revision' in transaction['operation'] else None,
    grid=encode_navigation_grid(cells),goal=goal,goal_blocked=blocked(goal),replay=rows,physical_actions=0)
(out/'navigation.json').write_text(json.dumps(dict(geometry=geometry,observed_cells=cells),indent=2),encoding='utf-8')
(out/'result.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps(dict(goal=goal,goal_blocked=value['goal_blocked'],last=rows[-1]),indent=2))
