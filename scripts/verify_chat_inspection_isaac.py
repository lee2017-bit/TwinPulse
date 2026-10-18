# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual Isaac saved current-chat correction composition and rollback.

Output-reactive synthetic observations run through the shared mission first.
No measured room, live robot, provider call, Physics Run or browser is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False);state=output/'runtime'
    result={'status':'FAIL','observations':'OUTPUT_REACTIVE_SYNTHETIC_SHARED_MISSION',
        'isaac':'NOT_RUN','browser':'NOT_RUN','physical_validation':'NOT_RUN','robot_connections':0,'provider_calls':0,'checks':[]}
    sim=case=None
    sources=['scripts/verify_chat_inspection_isaac.py','packages/twinpulse_app/src/twinpulse_app/chat_inspection_visual.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
        'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
        'packages/twinpulse_app/src/twinpulse_app/chat_inspection.py',
        'packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py','packages/twinpulse_app/src/twinpulse_app/command_broker.py',
        'packages/twinpulse_core/src/twinpulse_core/engine_contracts.py',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'extensions/twinpulse.extension/twinpulse/extension/bedroom_preview.py',
        'apps/twinpulse-web/src/ChatInspectionBuild.tsx','apps/twinpulse-web/src/ChatWorkspace.tsx',
        'apps/twinpulse-web/src/conversation-types.ts','apps/twinpulse-web/src/api.ts',
        'scripts/twinpulse_backend.py','packages/twinpulse_app/src/twinpulse_app/process_manager.py',
        'extensions/twinpulse.extension/twinpulse/extension/extension.py']
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    try:
        from tests.integration.test_chat_inspection_visual import cold_tests
        from twinpulse_app.chat_inspection_visual import KIND,checked_inspection_visual
        from twinpulse_core import CommandEnvelope
        from twinpulse_core.site_contracts import SceneRevision
        case=cold_tests.ColdStartTests();case.setUp();case.root=state
        job,adapter,report=case.execute('current_chat',1.,[0.,-.6,0.],[0.,0.],mode='SURVEY_ONLY',photo_policy='correct_walls',current_chat=True)
        assert job['state']=='MISSION_ARRIVED',job.get('error')
        assert adapter.velocity==(0.,0.) and report['cold_start']['stage']=='SURVEY_COMPLETE'
        descriptor={'kind':KIND,'mission_id':job['job_id'],'manifest_sha256':job['report_revision']}
        scene,visual=checked_inspection_visual(state,'current_chat',descriptor)
        source=SceneRevision.from_dict(report['room_source']['scene'])
        assert scene.parent_revision==source.revision and scene.revision!=source.revision
        result['checks'].append('shared_survey_fit_correction_fresh_revalidation_saved_report_no_goal')
        originals={str(p.relative_to(state)):hashlib.sha256(p.read_bytes()).hexdigest() for p in state.rglob('*.json')}
        from isaacsim import SimulationApp
        sim=SimulationApp({'headless':True,'width':960,'height':720})
        import omni.usd,omni.timeline
        from pxr import Usd,UsdGeom,UsdPhysics
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.bedroom_preview import PREVIEW_PATH
        omni.usd.get_context().new_stage()
        for _ in range(8):sim.update()
        stage=omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage,'/ExternalKeep').GetPrim().SetCustomDataByKey('marker','preserve')
        runtime=TwinPulseRuntime();engine=IsaacSimulationAdapter(runtime,project_id='current_chat',project_state_root=state)
        engine.update_control_lease('inspection-contract',True)
        def build(value,desc=None):
            payload={'artifact_id':'current-inspection','scene_revision':value.revision,'scene':value.to_dict()}
            if desc is not None:
                from twinpulse_core.presentation import DEFAULT_PRESENTATION
                payload['visual_preview']=desc;payload['presentation']={**DEFAULT_PRESENTATION,'view':'top'}
            command=CommandEnvelope(command_id=str(uuid4()),command_type='build_site_scene',project_id='current_chat',
                engine_session_id=engine.engine_session_id,stage_epoch=engine.stage_epoch,control_lease_id='inspection-contract',
                expected_applied_revision=value.revision,payload=payload,ttl_s=1.)
            return engine.execute(command)
        assert build(source).status=='succeeded'
        result['build']=build(scene,descriptor).to_dict();assert result['build']['status']=='succeeded',result['build']
        assert runtime.compiler.matches_site_scene(scene) and engine._applied_revision==scene.revision
        assert stage.GetPrimAtPath('/World/TwinPulse/Presentation').GetCustomDataByKey('twinpulseCameraSide')=='top'
        marker=stage.GetPrimAtPath(PREVIEW_PATH)
        assert marker.GetCustomDataByKey('poseStatus')=='HISTORICAL_SURVEY_CANDIDATE_NOT_CURRENT'
        assert marker.GetCustomDataByKey('currentPoseAvailable') is False
        assert marker.GetCustomDataByKey('motionAuthorized') is False
        model=stage.GetPrimAtPath(PREVIEW_PATH+'/Model');prims=list(Usd.PrimRange(model,Usd.TraverseInstanceProxies()))
        result['mesh_count']=sum(p.IsA(UsdGeom.Mesh) for p in prims)
        assert result['mesh_count']>0
        assert not any(p.HasAPI(UsdPhysics.RigidBodyAPI) or p.HasAPI(UsdPhysics.ArticulationRootAPI) or p.HasAPI(UsdPhysics.CollisionAPI) for p in prims)
        cloud=stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission/Scan')
        assert len(UsdGeom.Points(cloud).GetPointsAttr().Get())==len(visual['scan_room'])
        assert stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission').GetCustomDataByKey('annotationHeightIsPresentationOnly') is True
        wall_top=max(o.transform.position_m[2]+o.shape.dimensions_m[2]/2 for o in scene.objects if o.kind=='wall')
        assert all(p[2]>wall_top for p in UsdGeom.Points(cloud).GetPointsAttr().Get())
        result['checks'].append('actual_corrected_current_room_burger_scan_no_legacy_room_no_physics')
        before=stage.GetRootLayer().ExportToString()
        with patch('twinpulse.extension.bedroom_preview.compose_inspection_preview',side_effect=ValueError('INSPECTION_COMPOSITION_TEST_FAULT')):
            failure=build(scene,descriptor)
        assert failure.status=='failed',failure.to_dict()
        assert stage.GetRootLayer().ExportToString()==before and engine._applied_revision==scene.revision
        result['failure_receipt']=failure.to_dict();result['checks'].append('actual_post_build_failure_exact_owned_root_rollback')
        assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='preserve'
        assert not omni.timeline.get_timeline_interface().is_playing()
        saved=output/'current-survey-stage.usda';stage.GetRootLayer().Export(str(saved))
        reopened=Usd.Stage.Open(str(saved))
        assert reopened.GetPrimAtPath(PREVIEW_PATH).GetCustomDataByKey('currentPoseAvailable') is False
        assert all(hashlib.sha256((state/p).read_bytes()).hexdigest()==h for p,h in originals.items())
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        result.update(status='PASS',isaac='ACTUAL_COMPOSITION_ROLLBACK_AND_USD_REOPEN_PASS',source_sha256=hashes,
                      scene_revision=scene.revision,original_scene_revision=source.revision,report_revision=job['report_revision'])
        result['checks'].append('saved_usd_historical_marker_original_json_external_prim_preserved')
    except Exception as exc:
        import traceback
        traceback.print_exc();result.update(error_type=type(exc).__name__,error=str(exc)[:1000])
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if sim:sim.close()
        if case:case.doCleanups()
    print(json.dumps({k:result.get(k) for k in ('status','isaac','error')}),flush=True)
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
