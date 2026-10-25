# SPDX-License-Identifier: Apache-2.0
"""Actual OpenUSD in-memory stage QA; separate from installed Isaac UI proof."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

parser=argparse.ArgumentParser();parser.add_argument('resources',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args();resources=args.resources.resolve();repo=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(resources/'packages'/name/'src'))
sys.path.insert(0,str(resources/'scripts'))
from twinpulse_library_worker import load_existing_usd
load_existing_usd()
from pxr import Usd,UsdGeom
from twinpulse_core.environment_source import checked_environment
from twinpulse_core.environment_overlays import add_overlay,overlay_meshes
from twinpulse_core.environment_navigation import navigation_cells
from twinpulse_app.lidar_scene_geometry import scene_section

spec=importlib.util.spec_from_file_location('hybrid_author',resources/'extensions/twinpulse.extension/twinpulse/extension/environment_geometry.py')
author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
raw=(repo/'outputs/roomplan-lidar-review-20261024-02/environment.json').read_bytes()
environment=checked_environment(json.loads(raw));source_hash=hashlib.sha256(raw).hexdigest()
result=dict(scope='REAL_OPENUSD_STAGE_GEOMETRY_NOT_INSTALLED_UI_OR_HARDWARE',status='FAIL',source_sha256=environment['source_sha256'],environment_sha256=source_hash)

def stage(value):
    stage=Usd.Stage.CreateInMemory();root=UsdGeom.Xform.Define(stage,'/World/TwinPulse').GetPrim()
    root.SetCustomDataByKey('twinpulseSiteSceneRevision','geometry-qa')
    UsdGeom.Xform.Define(stage,author.ROOT);author.author_environment(stage,value)
    assert author.matches_environment(stage,value)
    return stage

def obstacle(x,y,kind='basket'):
    size=[.35,.3,.4] if kind=='basket' else [.3,.2,.04]
    return dict(item=dict(id='Added_'+'a'*20,kind=kind,label='Local photo estimate QA',catalog_version='room-items-1.0',
        position_m=[x,y,size[2]/2],dimensions_m=size,yaw_deg=0.,observation_time_utc=None),uncertainty_m=.2,
        evidence=dict(basis='manual_estimate',source_name=None,sha256=None,alignment_verified=False))

try:
    original_stage=stage(environment);base_section,_=scene_section(original_stage,.182)
    cells=navigation_cells(environment['meshes'])['cells'];free={(round(x,2),round(y,2)) for x,y,s,*_ in cells if s=='free'}
    selected=None
    # A deterministic test placement, expressly NOT photo-derived world pose.
    for x,y in sorted(free):
        if any((round(x+dx,2),round(y+dy,2)) not in free for dx in (-.2,0,.2) for dy in (-.2,0,.2)):continue
        if base_section.cast((x,y),(1,0))<1.4:continue
        try:mixed=add_overlay(environment,obstacle(x+1,y))
        except ValueError:continue
        selected=(x,y,mixed);break
    if selected is None:raise ValueError('NO_CLEAR_TEST_PLACEMENT')
    x,y,mixed=selected;st=stage(mixed);section,metadata=scene_section(st,.182)
    distance=section.cast((x,y),(1,0));expected=1-.35/2
    if abs(distance-expected)>1e-5:raise ValueError('VISIBLE_BASKET_FIRST_HIT_MISMATCH')
    if any('_uncertainty' in p or '_keepout' in p for p in metadata['surfaces']):raise ValueError('SYNTHETIC_SENSOR_SURFACE')
    low=add_overlay(environment,obstacle(x+1,y,'cable_bundle'));lowstage=stage(low);lowsection,_=scene_section(lowstage,.182)
    if abs(lowsection.cast((x,y),(1,0))-base_section.cast((x,y),(1,0)))>1e-5:raise ValueError('LOW_CABLE_INVENTED_TALL_RETURN')
    nav=navigation_cells(low['meshes']+overlay_meshes(low))
    states={(round(a,2),round(b,2)):s for a,b,s,*_ in nav['cells']}
    if states[(round(x+1,2),round(y,2))]!='occupied':raise ValueError('LOW_CABLE_NOT_BLOCKING_NAVIGATION')
    geom=st.GetPrimAtPath(author.ROOT+'/Added_'+'a'*20+'_uncertainty/geometry')
    geom.SetCustomDataByKey('syntheticKeepout',False)
    if author.matches_environment(st,mixed):raise ValueError('TAMPERED_SYNTHETIC_FLAG_ACCEPTED')
    (out/'mixed-environment.json').write_text(json.dumps(mixed,indent=2),encoding='utf-8')
    result.update(status='PASS',robot_pose=[x,y,0],obstacle_xy=[x+1,y],nominal_height_m=.182,
        first_hit_m=distance,expected_visual_first_hit_m=expected,synthetic_front_distance_m=.625,
        low_cable_first_hit_m=lowsection.cast((x,y),(1,0)),base_first_hit_m=base_section.cast((x,y),(1,0)),
        source_meshes_unchanged=mixed['meshes']==environment['meshes'],synthetic_sensor_surfaces=0,
        low_cable_navigation='occupied',synthetic_tamper_rejected=True,
        placement_basis='DETERMINISTIC_TEST_COORDINATES_NOT_PHOTO_OR_WORLD_ALIGNMENT')
except Exception as error:
    result['error']=str(error);raise
finally:
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
