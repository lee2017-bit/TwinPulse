# SPDX-License-Identifier: Apache-2.0
"""Actual saved SIM scan against a separately re-opened OpenUSD scene.

Geometric SIM fidelity only: no optical/real sensor or metric photo certificate.
"""
import hashlib,importlib.util,json,math,sys
from pathlib import Path
sys.dont_write_bytecode=True  # Never contaminate a verified installed package.
resources=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parents[1];evidence=root/'outputs/environment-photo-live-20261024-01'
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(resources/'packages'/name/'src'))
sys.path.insert(0,str(resources/'scripts'))
from twinpulse_library_worker import load_existing_usd
load_existing_usd()
from pxr import Usd,UsdGeom
from twinpulse_app.lidar_scene_geometry import scene_section
spec=importlib.util.spec_from_file_location('photo_geometry',resources/'extensions/twinpulse.extension/twinpulse/extension/environment_geometry.py')
author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
adopt=read(evidence/'adopt04/result.json');env=adopt['preview']['operation']['tool_call']['arguments']['environment']
sim_file=Path(sys.argv[3]) if len(sys.argv)>3 else evidence/'sim04/result.json'
sim=read(sim_file);scan=sim['scan']['scan'];x,y,yaw=scan['sensor_xy_yaw_world']
stage=Usd.Stage.CreateInMemory();UsdGeom.Xform.Define(stage,'/World/TwinPulse');UsdGeom.Xform.Define(stage,author.ROOT);author.author_environment(stage,env)
if not author.matches_environment(stage,env):raise ValueError('REAUTHORED_SCENE_MISMATCH')
section,metadata=scene_section(stage,scan['height_m']);errors=[];basket_hits=0
item=env['overlays'][0]['item'];cx,cy,_=item['position_m'];width,depth,_=item['dimensions_m']
for px,py in scan['points']:
    distance=math.hypot(px,py);angle=yaw+math.atan2(py,px)
    expected=section.cast((x,y),(math.cos(angle),math.sin(angle)))
    errors.append(abs(distance-expected))
    wx=x+px*math.cos(yaw)-py*math.sin(yaw);wy=y+px*math.sin(yaw)+py*math.cos(yaw)
    if abs(wx-(cx-width/2))<.001 and abs(wy-cy)<=depth/2+.001:basket_hits+=1
first=scan['points'][0];expected_front=cx-width/2-x
base=read(root/'outputs/roomplan-lidar-review-20261024-02/environment.json')
checks=dict(original_thirty_meshes_unchanged=env['meshes']==base['meshes'],
    actual_sensor_height=abs(scan['height_m']-.182)<1e-6,
    expected_new_sensor_pose=abs(x-1.318)<1e-6 and abs(y-1.15)<1e-6 and abs(yaw)<1e-6,
    first_basket_hit=abs(first[0]-expected_front)<.0002 and abs(first[1])<.0002,
    basket_hits_present=basket_hits>0,all_current_rays_match=max(errors)<.002,
    no_synthetic_returns=not any('_uncertainty' in s or '_keepout' in s for s in metadata['surfaces']))
result=dict(status='PASS_SIM_GEOMETRY' if all(checks.values()) else 'FAIL',checks=checks,
    scope='SAVED_SIM_SCAN_AND_REOPENED_OPENUSD_NOT_PHOTO_WORLD_OR_PHYSICAL_ALIGNMENT',
    scan_source=scan['source'],sensor_pose=[x,y,yaw],height_m=scan['height_m'],first_hit=first,expected_front_m=expected_front,
    ray_count=len(errors),basket_front_hits=basket_hits,max_ray_error_m=max(errors),
    source_sha256=env['source_sha256'],sim_result_sha256=hashlib.sha256(sim_file.read_bytes()).hexdigest())
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result));raise SystemExit(0 if all(checks.values()) else 1)
