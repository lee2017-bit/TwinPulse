# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual App cold mission -> authenticated engine bridge -> live USD display.

Isolated output-reactive synthetic sensors, no robot/paid provider/physics Run.
One normal owned room Build precedes mission. No pose or success injection.
"""
import argparse
import errno
import hashlib
import json
from pathlib import Path
import secrets
import os
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--browser-case',choices=('normal','storage'))
    parser.add_argument('--playwright-module',type=Path)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False);state=output/'isolated-state'
    result={'status':'FAIL','source':'OUTPUT_REACTIVE_SYNTHETIC_RAYCAST','robot_connections':0,'provider_calls':0,
        'physical_validation':'NOT_RUN','physics_run':'NOT_RUN','browser_ui':'NOT_RUN','checks':[]}
    sim=server=bridge=automatic=mission=browser=broker=None;adapters=[];frames=[];active_receipts=[];fault_patch=None
    sources=[ROOT/p for p in ('scripts/verify_ad4_active_isaac.py','packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
        'packages/twinpulse_core/src/twinpulse_core/active_mission_visual.py',
        'packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py',
        'packages/twinpulse_core/src/twinpulse_core/local_navigation.py',
        'packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
        'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py','packages/twinpulse_robot_safety/mission_runtime.py',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py')]
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result['source_sha256']=hashes
    try:
        from tests.integration.test_automatic_photo_service import recipe
        from tests.integration.test_cold_start_mission import ColdAdapter
        from tests.integration.test_automatic_demo_service import GEOMETRY
        from tests.integration.test_a2_room_recipe import NoGateway
        from twinpulse_app.automatic_demo_service import AutomaticDemoService
        from twinpulse_app.automatic_mission_service import AutomaticMissionService
        from twinpulse_app.room_recipe import prepare_project_burger_visual,import_project_room_recipe
        from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore,LocalApiServer
        from scripts.rehearse_offline_app import NoCredentials
        pid='active_room';outline,_=recipe(state,pid,1.,import_now=False)
        prepare_project_burger_visual(state,pid,(0.,-.6,.002),0.);draft=import_project_room_recipe(state,pid)
        automatic=AutomaticDemoService(state,pid,geometry_loader=lambda:GEOMETRY);adapters=[]
        def factory(prior,room,effective,goal):
            adapter=ColdAdapter(prior,room,effective,goal,outline=outline,start=[0.,-.6,0.])
            adapters.append(adapter);return adapter
        factory.supports_local_correction=True
        mission=AutomaticMissionService(automatic,adapter_factory=factory)
        app=ApplicationService(NoGateway(),project_store=ProjectStore.for_project(state,pid),project_id=pid)
        broker=CommandBroker(project_id=pid)
        workflow=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
        workflow.continue_room_recipe();artifact=next(iter(broker._site_scenes.values()))
        original=app._project_store.path.read_bytes()
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
        broker.register_engine(engine.engine_session_id,engine.stage_epoch);lease=broker.acquire_lease('product')
        engine.update_control_lease(lease['control_lease_id'],True);broker.record_snapshot(engine.snapshot())
        broker.submit('product',{'client_request_id':'active-owned-room-build','command_type':'build_site_scene',
            'artifact_id':artifact.artifact_id,'expected_applied_revision':artifact.revision})
        command=broker.claim(engine.engine_session_id,engine.stage_epoch);receipt=engine.execute(command)
        broker.record_receipt(receipt);assert receipt.status=='succeeded',receipt.error_code
        secret=secrets.token_urlsafe(32);product_secret=secrets.token_urlsafe(32)
        server=LocalApiServer(broker,product_bootstrap_secret=product_secret,engine_bootstrap_secret=secret,
            product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',session_history_root=state,credential_store=NoCredentials())
        server.automatic_mission.close();server.automatic_demo.close();server.automatic_demo=automatic;server.automatic_mission=mission
        server.start();bridge=BridgeClient(engine,base_url=server.base_url,bootstrap_secret=secret);bridge.start()
        end=time.monotonic()+10
        while not bridge.connected and time.monotonic()<end:sim.update();bridge.update();time.sleep(.01)
        assert bridge.connected,'BRIDGE_NOT_CONNECTED'
        revision=mission.readiness(None)['room_revision']
        if args.browser_case:
            if not args.playwright_module or not args.playwright_module.is_file():raise ValueError('EXISTING_PLAYWRIGHT_REQUIRED')
            chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
            node=shutil.which('node')
            if not node or not chrome.is_file():raise ValueError('EXISTING_BROWSER_RUNTIME_REQUIRED')
            if args.browser_case=='storage':
                original_open=Path.open
                def fail_report(path,*a,**kw):
                    mode=a[0] if a else kw.get('mode','r')
                    if 'automatic-mission' in path.parts and mode=='x':raise OSError(errno.ENOSPC,'PRIVATE_ERROR_CANARY')
                    return original_open(path,*a,**kw)
                fault_patch=patch.object(Path,'open',fail_report);fault_patch.start()
            environment=dict(os.environ,TWINPULSE_REHEARSAL_URL=server.base_url,TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                TWINPULSE_REHEARSAL_OUTPUT=str(output),TWINPULSE_REHEARSAL_CHROME=str(chrome),
                TWINPULSE_PLAYWRIGHT_MODULE=str(args.playwright_module.resolve()),TWINPULSE_PACKAGE_CASE=args.browser_case)
            browser=subprocess.Popen([node,str(ROOT/'apps/twinpulse-web/e2e/packaged-mission-isaac.mjs')],
                env=environment,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            result['browser_ui']='EXECUTING_ACTUAL_PACKAGED_WEB'
        else:mission.start('product',None,{'mode':'SURVEY_THEN_NAVIGATE','xy':[.15,-.6],'room_revision':revision,'duration_s':45.})
        end=time.monotonic()+150;renew=0.;seen=None
        while (browser.poll() is None if browser else mission.worker.is_alive()) and time.monotonic()<end:
            now=time.monotonic()
            if not browser and now>=renew:broker.renew_lease('product',lease['control_lease_id']);renew=now+1
            # The Web owns its mission. Do not bypass authorization to publish
            # a snapshot as a different fixture owner.
            sim.update();bridge.update()
            with mission.lock:
                # Start may arrive between renderer ticks. Reading owner and
                # snapshot separately used the fixture owner for the new Web
                # job, correctly rejected by the product authorization gate.
                observed=mission.snapshot(mission.job['owner'])['job'] if mission.job else None
            if not observed:time.sleep(.005);continue
            display=observed.get('isaac_display',{})
            if display.get('status')=='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED':
                active_receipts.append({'job_id':observed['job_id'],'sequence':display['sequence'],'state':observed['state']})
            assert not omni.timeline.get_timeline_interface().is_playing()
            cursor=engine._mission_visual_cursor
            if cursor and cursor!=seen:
                seen=cursor;marker=stage.GetPrimAtPath(PREVIEW_PATH);xy=marker.GetAttribute('xformOp:translate').Get()
                overlay=stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission')
                frames.append({'job_id':cursor[0],'sequence':cursor[1],'position':list(xy),
                    'revision':overlay.GetCustomDataByKey('revision'),'pose_status':marker.GetCustomDataByKey('poseStatus')})
            time.sleep(.005)
        if browser:
            assert browser.poll() is not None,'BROWSER_DEADLINE'
            result['browser']=json.loads((output/'browser-result.json').read_text(encoding='utf-8'))
            assert browser.returncode==0 and result['browser']['status']=='PASS','PACKAGED_BROWSER_FAILED'
        assert mission.worker and not mission.worker.is_alive(),'MISSION_WORKER_DEADLINE'
        job=mission.snapshot(mission.job['owner'])['job'];result['mission_state']=job['state']
        if args.browser_case=='storage':
            assert job['state']=='FAILED' and job['report_errno']==28 and job['visual']['pose_room'] is None
            assert 'PRIVATE_ERROR_CANARY' not in json.dumps(job)
        else:assert job['state']=='MISSION_ARRIVED',(job['state'],job.get('error'))
        assert len(frames)>=3,('INSUFFICIENT_ACTIVE_FRAMES',len(frames),bridge.last_error,bridge.mission_visual_status)
        assert len({tuple(round(v,4) for v in row['position']) for row in frames})>=2
        assert all(row['pose_status']=='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED' for row in frames)
        assert active_receipts,'NO_CURRENT_RENDERER_ACK_DURING_ACTIVE_MISSION'
        assert job.get('isaac_display',{}).get('status')=='NO_ACTIVE_MISSION','TERMINAL_RENDERER_RECEIPT_MUST_NOT_BE_CURRENT'
        assert all(a.halted and a.velocity==(0.,0.) for a in adapters)
        # Terminal/stale display is explicitly a last observation, not live pose.
        end=time.monotonic()+1.2
        while time.monotonic()<end:sim.update();bridge.update();time.sleep(.01)
        terminal_pose_status=stage.GetPrimAtPath(PREVIEW_PATH).GetCustomDataByKey('poseStatus')
        assert terminal_pose_status in ('LAST_OBSERVATION_NOT_CURRENT','CURRENT_SENSOR_CANDIDATE_SAVED_REPORT_NOT_CALIBRATED')
        result['terminal_pose_status']=terminal_pose_status
        assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='preserve'
        if not args.browser_case:assert runtime.compiler.matches_site_scene(draft.site.scene)
        else:
            assert engine._mission_geometry_receipts,'NO_DERIVED_GEOMETRY_RENDER_RECEIPT'
            result['geometry_receipts']=list(engine._mission_geometry_receipts)
        assert app._project_store.path.read_bytes()==original
        assert len(broker._operations)==(2 if args.browser_case=='normal' else 1)
        result['checks']=['one_cold_start_actual_fit_goal_no_prior','authenticated_API_bridge_main_thread_USD_multiple_active_poses',
            'engine_stage_project_geometry_owned_lease_bound','renderer_status_returned_to_App',
            'terminal_last_observation_not_current','original_project_external_prim_preserved','timeline_never_started']
        result['frames']=frames;result['isaac']='ACTIVE_VISUAL_RUNTIME_PASS'
        result['browser_ui']='PASS' if browser else 'NOT_RUN'
        result['import_origins']={name:str(Path(sys.modules[name].__file__).resolve()) for name in
            ('twinpulse_app.api','twinpulse_app.automatic_mission_service','twinpulse.extension.isaac_adapter')}
        assert all(Path(p).is_relative_to(ROOT) for p in result['import_origins'].values())
        (output/'synthetic-raw.json').write_text(json.dumps({'provenance':'synthetic_raycast','physical_validation':'NOT_RUN',
            'observations':adapters[0].raw,'commands':adapters[0].sent},allow_nan=False),encoding='utf-8')
        stage.GetRootLayer().Export(str(output/'active-mission-stage.usda'))
        if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p.relative_to(ROOT))] for p in sources):raise ValueError('SOURCE_CHANGED_DURING_TEST')
        result['status']='PASS'
    except Exception as exc:
        import traceback
        traceback.print_exc();result.update(error_type=type(exc).__name__,reason=str(exc)[:250])
    finally:
        if browser and browser.poll() is None:
            browser.terminate();browser.wait(timeout=10)
        if fault_patch:fault_patch.stop()
        if broker:
            result['broker_operations']=[operation.public() for operation in broker._operations.values()]
        if bridge:result['bridge_visual_status']=bridge.mission_visual_status
        if bridge:bridge.stop()
        if server:server.stop()
        else:
            if mission:mission.close()
            if automatic:automatic.close()
        result['frames']=frames;result['active_receipts']=active_receipts
        if mission and mission.job:
            (output/'mission-job.json').write_text(json.dumps({k:v for k,v in mission.job.items() if k!='owner'},allow_nan=False),encoding='utf-8')
        if adapters:
            (output/'synthetic-raw.json').write_text(json.dumps({'provenance':'synthetic_raycast','physical_validation':'NOT_RUN',
                'observations':adapters[0].raw,'commands':adapters[0].sent,'final_velocity':list(adapters[0].velocity)},allow_nan=False),encoding='utf-8')
        (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:result.get(k) for k in ('status','isaac','reason','mission_state','physical_validation')}),flush=True)
        if sim:sim.close()
    return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
