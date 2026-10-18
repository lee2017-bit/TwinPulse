# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual local USD rollback, diverse scenes and stopped PhysX fault contracts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    result=dict(status='FAIL',physics='actual_local_Isaac',generation='explicit_local_tool_plans',
                photo_inference='NOT_RUN',robot_connections=0,paid_calls=0,checks=[],scenes=[])
    app=None;runtime=None
    paths=['scripts/verify_sim_fault_transactions.py','extensions/twinpulse.extension/twinpulse/extension/scene_compiler.py',
           'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py','extensions/twinpulse.extension/twinpulse/extension/runtime.py',
           'packages/twinpulse_core/src/twinpulse_core/site_simulation.py','packages/twinpulse_app/src/twinpulse_app/simulation_assets.py']
    result['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    try:
        from isaacsim import SimulationApp
        app=SimulationApp({'headless':True,'width':960,'height':640})
        import omni.usd
        from pxr import UsdGeom,UsdPhysics,Gf
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse_app.manual_room import manual_room_plan
        from twinpulse_app.simulation_assets import burger_inventory
        from twinpulse_core import CommandEnvelope,SceneToolCall,SiteToolPlan
        from twinpulse_core.site_tools import execute_site_tool_plan
        from twinpulse_core.simulation_goal import preview_review
        omni.usd.get_context().new_stage()
        for _ in range(8):app.update()
        stage=omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage,'/ExternalKeep').GetPrim().SetCustomDataByKey('marker','unchanged')
        runtime=TwinPulseRuntime();engine=IsaacSimulationAdapter(runtime,project_id='fault_contract')
        engine.update_control_lease('contract-lease',True)
        def command(kind,scene,payload):
            return CommandEnvelope(command_id=str(uuid4()),command_type=kind,project_id=engine.project_id,
                engine_session_id=engine.engine_session_id,stage_epoch=engine.stage_epoch,control_lease_id='contract-lease',
                expected_applied_revision=scene.revision,payload=payload,ttl_s=30.)
        def build(scene,plan):
            return command('build_site_scene',scene,dict(artifact_id='fixture',scene_revision=scene.revision,
                scene=scene.to_dict(),simulation_preview=plan))
        plans=[('bedroom',manual_room_plan('bedroom',5.,6.,2.6,[{'kind':'bed','center_m':[-1.2,1.4],'yaw_deg':0},
                    {'kind':'desk','center_m':[1.2,1.4],'yaw_deg':0}])),
               ('living_room',manual_room_plan('living_room',6.,7.,2.6,[{'kind':'sofa','center_m':[-1.4,1.6],'yaw_deg':90},
                    {'kind':'dining_table','center_m':[1.4,1.6],'yaw_deg':0},{'kind':'storage','center_m':[-1.6,-1.6],'yaw_deg':0}])),
               ('warehouse',SiteToolPlan('warehouse','Explicit warehouse fixture','No photo recognition',(
                    SceneToolCall('floor','create_floor',{'id':'floor','center_m':[0,0],'size_m':[7,8]}),
                    SceneToolCall('rack','create_rack_row',{'id':'rack','center_m':[1.5,1.5],'length_m':2.,
                        'depth_m':.5,'height_m':1.8,'bay_count':2,'level_count':2}))))]
        for label,tool_plan in plans:
            scene=execute_site_tool_plan(tool_plan,source='manual',source_ref=hashlib.sha256(label.encode()).hexdigest()).scene
            plan=preview_review(scene,burger_inventory())['plan']
            receipt=engine.execute(build(scene,plan));assert receipt.status=='succeeded',receipt
            for _ in range(8):app.update()
            before=stage.GetRootLayer().ExportToString();old_receipt=runtime.compiler.build_receipt
            physics_prim=stage.GetPrimAtPath('/World/TwinPulse/PhysicsScene')
            old_applied=engine._applied_revision
            preview=stage.GetPrimAtPath('/World/TwinPulse/Presentation/BurgerPhotoPreview')
            assert preview and not runtime._timeline.is_playing()
            # Force a late mutation followed by an exception. Cached scene
            # identity and exact owned visual must come from the saved USD.
            def fail_after_mutation(compiler,value):
                UsdGeom.Xform.Define(compiler.stage,'/World/TwinPulse/Presentation/FaultMarker')
                raise ValueError('SIM_POST_COMPOSE_INJECTED_FAULT')
            with patch('twinpulse.extension.bedroom_preview.compose_simulation_preview',side_effect=fail_after_mutation):
                failed=engine.execute(build(scene,plan))
            assert failed.status=='failed' and failed.message=='SIM_POST_COMPOSE_INJECTED_FAULT'
            assert stage.GetRootLayer().ExportToString()==before,'USD_ROLLBACK_CHANGED'
            assert physics_prim.IsValid(),'PHYSICS_SCENE_HANDLE_EXPIRED'
            assert runtime.compiler.build_receipt==old_receipt and engine._applied_revision==old_applied
            assert runtime.compiler.matches_site_scene(scene) and runtime.site_plan is None
            assert not runtime._timeline.is_playing() and not engine.snapshot().telemetry_available
            result['scenes'].append(dict(label=label,scene_revision=scene.revision,objects=len(scene.objects),
                asset_id=plan['asset_id'],rollback='EXACT_USD_AND_IDENTITY',failure=failed.to_dict()))
        result['checks'].append('Three scene families: real USD Build + exact post-composition rollback; external prim unchanged')
        run=command('run',scene,{'site_simulation':plan})
        receipt=engine.execute(run)
        assert receipt.status=='succeeded',receipt
        assert engine.execute(run)==receipt,'duplicate Run must be same receipt'
        for _ in range(45):app.update()
        with patch.object(runtime,'robot_pose_3d',side_effect=RuntimeError('SIM_TEST_POSE_LOST')):
            runtime._site_physics_step()
        fault=engine.snapshot()
        assert fault.runtime_state=='error' and fault.safety_state=='simulation_error'
        assert 'SIM_TEST_POSE_LOST' in fault.safety_reason and not fault.telemetry_available
        assert not runtime._timeline.is_playing()
        for name in ('wheel_left_joint','wheel_right_joint'):
            assert stage.GetPrimAtPath('/World/TwinPulse/SimBurger/Physics/'+name).GetAttribute('drive:angular:physics:targetVelocity').Get()==0.
        result['fault']=fault.to_dict()
        assert engine.execute(command('reset',scene,{})).status=='succeeded'
        assert runtime.site_plan is None and not stage.GetPrimAtPath('/World/TwinPulse/SimBurger')
        # Alter owned geometry during an explicit second run; the current
        # fault remains diagnosable even when its run/pose identity is dropped.
        assert engine.execute(command('run',scene,{'site_simulation':plan})).status=='succeeded'
        obj=stage.GetPrimAtPath('/World/TwinPulse/Environment/floor')
        obj.GetAttribute('xformOp:translate').Set(Gf.Vec3d(0,0,9))
        runtime._physics_steps=60;runtime._site_physics_step()
        invalid=engine.snapshot()
        assert invalid.runtime_state in {'stage_invalid','error'} and invalid.run_id is None
        assert not invalid.telemetry_available and not runtime._timeline.is_playing()
        result['invalidated']=invalid.to_dict()
        assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='unchanged'
        result['checks']+=['Actual PhysX fault zeroes wheel drives and pauses timeline; original cause preserved',
            'Duplicate Run returns cached receipt; explicit Reset clears telemetry, never resumes',
            'Geometry identity loss clears current run/pose and remains a fault; external prim unchanged']
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in result['source_sha256'].items())
        result['status']='PASS'
    except Exception as error:
        import traceback
        traceback.print_exc();result.update(error_type=type(error).__name__,error=str(error)[:1600])
    finally:
        if runtime:runtime.shutdown()
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('SIM_FAULT_TRANSACTIONS='+result['status'],flush=True)
        if app:app.close()
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
