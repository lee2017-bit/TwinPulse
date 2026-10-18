# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual adapter Build/rebuild/export of reusable household and warehouse models.

Synthetic dimensions, zero provider/robot connections. Output must be a fresh
owned directory. Never touch the user's original room or active project.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import traceback
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))


def gallery_plan(warehouse=False):
    from twinpulse_core import SceneToolCall, SiteToolPlan
    from twinpulse_core.model_library import PARAMETRIC_FURNITURE_VERSION
    calls=[SceneToolCall('floor','create_floor',dict(id='floor',center_m=[0,0],size_m=[12,10]))]
    if warehouse:
        calls += [SceneToolCall('rack','create_rack_row',dict(id='rack',center_m=[-2,2],length_m=5.,depth_m=.9,height_m=2.6,bay_count=3,level_count=3)),
            SceneToolCall('pallet','place_pallet_stack',dict(id='pallet',center_m=[2,-1],footprint_m=[1.2,.8],stack_height_m=1.,stack_levels=3))]
    else:
        for kind,center,size,variant,finish in (
            ('bed',[-3,-2],[1.6,2.2,1.],'double','natural'),
            ('wardrobe',[0,3],[1.8,.7,2.2],'open','white'),
            ('desk',[3,3],[1.8,.8,.8],'metal','natural'),
            ('chair',[3,1],[.5,.5,1.],'upholstered','natural'),
            ('sofa',[-3,2],[2.1,.9,.9],'three_seat','natural'),
            ('dining_table',[0,-2],[1.8,1.,.8],'wood','dark'),
            ('storage',[3,-2],[1.,.5,1.1],'closed','white')):
            calls.append(SceneToolCall(kind,'place_furniture',dict(id=kind,kind=kind,
                catalog_version=PARAMETRIC_FURNITURE_VERSION,center_m=center,yaw_deg=0,
                dimensions_m=size,variant=variant,finish=finish)))
    return SiteToolPlan('library_gallery','Synthetic reusable catalog; not photo reconstruction','No photo inference',tuple(calls),plan_version='2.2')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--diagnose-light',action='store_true',help='Explicit diagnostic only; temporarily toggle owned lights in synthetic stage')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    result=dict(status='FAIL',provider_calls=0,robot_connections=0,physical_validation='NOT_RUN',checks=[])
    app=None
    try:
        from isaacsim import SimulationApp
        app=SimulationApp(dict(headless=True,width=1280,height=960))
        import omni.usd
        from pxr import Gf,Usd,UsdGeom,UsdPhysics
        from omni.kit.viewport.utility import get_active_viewport,capture_viewport_to_file
        from twinpulse_core import CommandEnvelope
        from twinpulse_app.application import ApplicationService
        from twinpulse_app.site_draft import SiteDraftRecord
        from twinpulse_app.project_store import ProjectRecord,ProjectStore
        from twinpulse_app.scene_changes import SceneChangeStore
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.room_visuals import PATH
        for case in ('home','warehouse'):
            context=omni.usd.get_context();context.new_stage()
            for _ in range(10):app.update()
            plan=gallery_plan(case=='warehouse')
            prepared=ApplicationService.prepare_input(prompt='Synthetic '+case+' library gallery',images=(),measurement_constraints=(),generation_settings={'model_id':'offline'})
            draft=SiteDraftRecord.create(request_id=case,provider_name='local-catalog-fixture',model_id='none',image_count=0,input_revision=prepared.revision,plan=plan)
            state=output/case;store=ProjectStore.for_project(state,'default')
            store.save(ProjectRecord('default',latest_input=prepared.revision,site_draft=draft))
            runtime=TwinPulseRuntime();adapter=IsaacSimulationAdapter(runtime,project_state_root=state)
            adapter.update_control_lease('library-test',True)
            def build(scene):
                receipt=adapter.execute(CommandEnvelope(command_id='build_'+uuid4().hex,command_type='build_site_scene',project_id='default',
                    engine_session_id=adapter.engine_session_id,stage_epoch=adapter.stage_epoch,control_lease_id='library-test',
                    expected_applied_revision=scene.revision,payload=dict(artifact_id='library-fixture',scene_revision=scene.revision,scene=scene.to_dict())))
                assert receipt.status=='succeeded',(receipt.error_code,receipt.message)
                assert runtime.compiler.matches_site_scene(scene)
                stage=context.get_stage();root=stage.GetPrimAtPath(PATH)
                groups=[p for p in root.GetChildren() if p.GetName().startswith('Item_')]
                assert len(groups)==(7 if case=='home' else 2)
                assert all(p.GetCustomDataByKey('libraryModelId') for p in groups)
                assert all(not p.HasAPI(api) for p in Usd.PrimRange(root) for api in (UsdPhysics.CollisionAPI,UsdPhysics.RigidBodyAPI,UsdPhysics.ArticulationRootAPI))
                return stage,groups
            scene=draft.site.scene;stage,groups=build(scene)
            def capture(label):
                viewport=get_active_viewport();camera=UsdGeom.Camera(stage.GetPrimAtPath('/World/TwinPulse/Presentation/Camera'))
                camera.ClearXformOpOrder();camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(9,-12,9),Gf.Vec3d(0,.5,.9),Gf.Vec3d(0,0,1)).GetInverse())
                camera.CreateFocalLengthAttr(30);viewport.set_active_camera(str(camera.GetPath()))
                # Let asynchronous RTX material invalidation settle after a rebuild.
                for _ in range(120):
                    app.update();time.sleep(.01)
                capture_viewport_to_file(viewport,str(output/(label+'.png')))
                for _ in range(60):
                    app.update();time.sleep(.01)
                assert (output/(label+'.png')).is_file()
                from PIL import Image,ImageStat
                with Image.open(output/(label+'.png')) as frame:
                    rgb=frame.convert('RGB');mean=sum(ImageStat.Stat(rgb).mean)/3
                result.setdefault('frame_mean_rgb',{})[label]=mean
                if not args.diagnose_light:assert 20.<mean<245.,('Unusable dark/overexposed library frame',label,mean)
            capture(case+'-models')
            result[case]=dict(groups=len(groups),meshes=sum(p.IsA(UsdGeom.Mesh) for p in Usd.PrimRange(stage.GetPrimAtPath(PATH))),
                scene_revision=scene.revision,model_ids=[p.GetCustomDataByKey('libraryModelId') for p in groups])
            if case=='home':
                camera_schema=stage.GetPrimAtPath('/World/TwinPulse/Presentation/Camera').GetAppliedSchemas()
                original=store.path.read_bytes();changes=SceneChangeStore(store.path.with_suffix('.scene-changes.json'),project_id='default',source=draft,project_store=store)
                call=next(c for c in plan.calls if c.call_id=='bed')
                updated=replace(call,arguments={**call.arguments,'dimensions_m':[.9,1.9,.75],'variant':'single','finish':'white'})
                preview=changes.load().preview(draft,operation_id='resize',mode='change',target_call_id='bed',tool_call=updated.to_dict())
                changes.apply(preview['operation'],preview['preview_digest']);next_plan,next_site=changes.load().replay(draft)
                stage,_=build(next_site.scene)
                marker=stage.GetPrimAtPath(PATH+'/Item_bed')
                assert tuple(marker.GetCustomDataByKey('dimensionsM'))==(.9,1.9,.75)
                assert marker.GetCustomDataByKey('variant')=='single' and marker.GetCustomDataByKey('finish')=='white'
                assert not stage.GetPrimAtPath(PATH+'/Item_bed/pillow_1')
                assert stage.GetPrimAtPath('/World/TwinPulse/Presentation/Camera').GetAppliedSchemas()==camera_schema
                assert store.path.read_bytes()==original
                capture('home-resized-single-bed')
                # Diagnose a hot-rebuild renderer failure without changing any
                # product lighting policy or interpreting an overexposed frame as PASS.
                if args.diagnose_light:
                    from pxr import UsdLux
                    lights=[UsdLux.LightAPI(p) for p in stage.Traverse() if p.HasAPI(UsdLux.LightAPI)]
                    intensities=[light.GetIntensityAttr().Get() for light in lights]
                    result['hot_rebuild_lights']=[dict(path=str(light.GetPrim().GetPath()),intensity=value) for light,value in zip(lights,intensities)]
                    for light in lights:light.GetIntensityAttr().Set(0.)
                    for _ in range(40):app.update()
                    capture('home-light-zero-diagnostic')
                    for light,value in zip(lights,intensities):light.GetIntensityAttr().Set(value)
                    capture('home-light-restored-diagnostic')
                scene=next_site.scene
                result['checks'].append('actual whole bed resize/variant/finish through saved sidecar+adapter; original unchanged')
            stage.GetRootLayer().Export(str(output/(case+'.usda')))
            reopened=Usd.Stage.Open(str(output/(case+'.usda')))
            assert reopened.GetPrimAtPath(PATH).GetCustomDataByKey('sceneRevision')==scene.revision
            result['checks'].append(case+': actual adapter Build/library markers/display physics0/export reopen PASS')
        result['status']='PASS'
    except Exception as error:result.update(error=str(error),traceback=traceback.format_exc())
    finally:
        paths=['packages/twinpulse_core/src/twinpulse_core/'+name+'.py' for name in ('model_library','furniture','room_visuals','tool_catalog','site_tools')]
        paths += ['scripts/verify_model_library_isaac.py','extensions/twinpulse.extension/twinpulse/extension/scene_compiler.py',
                  'extensions/twinpulse.extension/twinpulse/extension/room_visuals.py']
        from hashlib import sha256
        result['source_sha256']={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('MODEL_LIBRARY_ISAAC='+result['status'],flush=True)
        if app:app.close()
    print('MODEL_LIBRARY_ISAAC='+result['status'],flush=True)
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
