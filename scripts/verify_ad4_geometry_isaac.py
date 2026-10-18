# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual owned USD geometry transaction and negative display contracts.

An explicitly constructed synthetic ledger exercises rendering, not photo fit,
sensor localization, browser acceptance or physical movement. Never runs physics.
"""
import argparse
import copy
import difflib
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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False);state=output/'isolated-state'
    result={'status':'FAIL','source':'SYNTHETIC_LEDGER_RENDERING_CONTRACT','robot_connections':0,'provider_calls':0,
            'physical_validation':'NOT_RUN','physics_run':'NOT_RUN','browser_ui':'NOT_RUN','checks':[]};sim=None
    sources=[ROOT/p for p in ('scripts/verify_ad4_geometry_isaac.py',
        'packages/twinpulse_core/src/twinpulse_core/active_mission_visual.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_visual.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_photo_store.py',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py')]
    result['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    try:
        from tests.integration.test_automatic_photo_service import recipe
        from twinpulse_app.room_recipe import prepare_project_burger_visual,import_project_room_recipe
        from twinpulse_app.automatic_photo_store import AutomaticPhotoStore,load_automatic_room
        from twinpulse_core import CommandEnvelope,canonical_sha256
        pid='geometry_room';recipe(state,pid,1.,import_now=False)
        manifest=prepare_project_burger_visual(state,pid,(0.,-.6,.002),0.);draft=import_project_room_recipe(state,pid)
        originals={str(p.relative_to(state)):p.read_bytes() for p in (state/'projects'/pid).glob('*.json')}
        from isaacsim import SimulationApp
        sim=SimulationApp({'headless':True,'width':960,'height':720})
        import omni.usd,omni.timeline
        from pxr import UsdGeom
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.bridge_client import BridgeClient
        from twinpulse.extension.bedroom_preview import PREVIEW_PATH
        omni.usd.get_context().new_stage()
        for _ in range(8):sim.update()
        stage=omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage,'/ExternalKeep').GetPrim().SetCustomDataByKey('marker','preserve')
        runtime=TwinPulseRuntime();engine=IsaacSimulationAdapter(runtime,project_id=pid,project_state_root=state)
        engine.update_control_lease('contract-lease',True)
        command=CommandEnvelope(command_id=str(uuid4()),command_type='build_site_scene',project_id=pid,
            engine_session_id=engine.engine_session_id,stage_epoch=engine.stage_epoch,control_lease_id='contract-lease',
            expected_applied_revision=draft.site.scene.revision,payload={'artifact_id':'contract-room',
                'scene_revision':draft.site.scene.revision,'scene':draft.site.scene.to_dict(),
                'visual_preview':{'kind':'project_room_visual_v1','manifest_sha256':manifest['manifest_sha256']}},ttl_s=1.)
        assert engine.execute(command).status=='succeeded'
        before=engine.mission_objects_revision();room=load_automatic_room(state,pid)
        store=AutomaticPhotoStore(state,pid);after=copy.deepcopy(store.current(room)['objects'])
        next(o for o in after if o['kind']=='wall')['transform']['position_m'][1]+=.1
        event=store.append(room,None,after,action='apply',job_id='a'*32,map_revision='b'*64)
        body={'schema':'active-mission-geometry-1.0','engine_session_id':engine.engine_session_id,
            'stage_epoch':engine.stage_epoch,'project_id':pid,'job_id':'a'*32,'sequence':2,
            'previous_objects_revision':before,'objects_revision':canonical_sha256(after),'correction_revision':event['revision']}
        geometry={**body,'revision':canonical_sha256(body)}
        def reject(value,reason):
            try:engine.update_mission_geometry(value)
            except ValueError as exc:assert str(exc)==reason,(str(exc),reason)
            else:raise AssertionError('UNEXPECTED_GEOMETRY_ACCEPTANCE')
            assert engine.mission_objects_revision()==before
            assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='preserve'
            result['checks'].append(reason)
        engine.update_control_lease(None,False);reject(geometry,'ACTIVE_VISUAL_LEASE_OR_TIMELINE')
        engine.update_control_lease('contract-lease',True)
        for key,value in (('engine_session_id','other'),('stage_epoch','other'),('project_id','other'),
                          ('previous_objects_revision','c'*64)):
            bad={**body,key:value};reject({**bad,'revision':canonical_sha256(bad)},'ACTIVE_VISUAL_ENGINE_OR_ROOM_CHANGED')
        bad={**body,'correction_revision':'c'*64}
        reject({**bad,'revision':canonical_sha256(bad)},'ACTIVE_GEOMETRY_CORRECTION_CHANGED')
        old_applied=engine._applied_revision;old_stage=stage.GetRootLayer().ExportToString()
        # Inject a failure only, after the real USD geometry build begins.
        # Existing owned-root rollback must preserve the last good scene/model.
        bridge=BridgeClient(engine,base_url='http://127.0.0.1:1',bootstrap_secret='x'*32,clock=lambda:10.)
        bridge._lease_valid=True;bridge._lease_id='contract-lease';bridge._last_success=10.
        bridge._mission_geometry=geometry;bridge._mission_received=10.
        with patch('twinpulse.extension.bedroom_preview.compose_bedroom_preview',side_effect=ValueError('GEOMETRY_VISUAL_COMPOSE_FAULT')):
            bridge.update()
        receipt=bridge._mission_result
        assert receipt['status']=='ACTIVE_GEOMETRY_RENDER_FAILED' and receipt['error_code']=='GEOMETRY_VISUAL_COMPOSE_FAULT'
        assert receipt['error_type']=='ValueError';assert engine._applied_revision==old_applied
        assert engine.mission_objects_revision()==before and stage.GetPrimAtPath(PREVIEW_PATH).IsValid()
        restored_stage=stage.GetRootLayer().ExportToString()
        if restored_stage!=old_stage:
            (output/'rollback-before.usda').write_text(old_stage,encoding='utf-8')
            (output/'rollback-after.usda').write_text(restored_stage,encoding='utf-8')
            (output/'rollback.diff').write_text(''.join(difflib.unified_diff(
                old_stage.splitlines(keepends=True),restored_stage.splitlines(keepends=True),
                fromfile='before',tofile='after')),encoding='utf-8')
            result['rollback_stage_sha256']={'before':hashlib.sha256(old_stage.encode()).hexdigest(),
                                             'after':hashlib.sha256(restored_stage.encode()).hexdigest()}
            raise AssertionError('ACTUAL_USD_ROLLBACK_STAGE_DIFFERENT')
        assert not engine._mission_geometry_receipts
        result['failure_receipt']=receipt;result['checks'].append('actual_USD_post_build_fault_exact_rollback_no_success_receipt')
        bridge._mission_geometry=geometry;bridge._mission_received=9.4;bridge.update()
        assert bridge._mission_result['error_code']=='ACTIVE_GEOMETRY_PERMIT_EXPIRED'
        assert engine.mission_objects_revision()==before
        result['checks'].append('expired_main_thread_permission_rejected')
        # Explicit isolated evaluator call, not automatic retry after failure.
        engine.update_mission_geometry(geometry)
        assert engine.mission_objects_revision()==body['objects_revision']
        assert stage.GetPrimAtPath(PREVIEW_PATH).GetCustomDataByKey('poseStatus')=='STATIC_PREVIEW_NOT_CURRENT'
        assert len(engine._mission_geometry_receipts)==1 and engine._mission_visual_cursor is None
        try:engine.update_mission_geometry(geometry)
        except ValueError as exc:assert str(exc)=='ACTIVE_VISUAL_ENGINE_OR_ROOM_CHANGED'
        else:raise AssertionError('DUPLICATE_GEOMETRY_ACCEPTED')
        assert len(engine._mission_geometry_receipts)==1
        assert all((state/p).read_bytes()==b for p,b in originals.items())
        assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='preserve'
        assert not omni.timeline.get_timeline_interface().is_playing()
        stage.GetRootLayer().Export(str(output/'geometry-contract-stage.usda'))
        result['checks']+=['explicit_isolated_composition_static_pose_only','duplicate_geometry_rejected',
                          'project_original_external_prim_preserved_timeline_paused']
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==result['source_sha256'][str(p.relative_to(ROOT))] for p in sources)
        result.update(status='PASS',isaac='GEOMETRY_TRANSACTION_AND_NEGATIVE_CONTRACTS_RUNTIME_PASS')
    except Exception as exc:
        import traceback
        traceback.print_exc();result.update(error_type=type(exc).__name__,reason=str(exc)[:250])
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:result.get(k) for k in ('status','isaac','reason','physical_validation')}),flush=True)
        if sim:sim.close()
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
