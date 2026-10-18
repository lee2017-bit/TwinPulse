# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Built Web/API -> actual worker -> fresh sensor matching -> saved Twin view.

Output-reactive synthetic transport only. Optional existing Isaac runtime renders
the same immutable report; never starts physics, a provider or a robot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import queue
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--isaac',action='store_true');parser.add_argument('--cold',action='store_true')
    parser.add_argument('--correct-walls',action='store_true');parser.add_argument('--remote-pipe',action='store_true')
    parser.add_argument('--dense-scan',action='store_true',help='720-beam local synthetic transport; raw rays stay full')
    args=parser.parse_args()
    if args.correct_walls and not args.cold:parser.error('--correct-walls requires --cold')
    if args.remote_pipe and not (args.cold and args.correct_walls):parser.error('--remote-pipe requires --cold --correct-walls')
    if args.dense_scan and args.remote_pipe:parser.error('--dense-scan is a local synthetic transport check, not remote acceptance')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False);state=output/'isolated-state'
    from tests.integration.test_automatic_photo_service import recipe,RaycastSource
    from tests.integration.test_automatic_mission_service import RaycastAdapter
    from tests.integration.test_automatic_demo_service import GEOMETRY
    from tests.integration.test_a2_room_recipe import NoGateway
    from twinpulse_app.automatic_demo_service import AutomaticDemoService
    from twinpulse_app.automatic_mission_service import AutomaticMissionService
    from twinpulse_app.automatic_mission_visual import checked_mission_visual
    from twinpulse_app.room_recipe import prepare_project_burger_visual,import_project_room_recipe
    from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore,LocalApiServer
    from rehearse_offline_app import NoCredentials
    pid='mission_room'
    automatic=AutomaticDemoService(state,pid,source_factory=lambda *a:RaycastSource(pid,outline),geometry_loader=lambda:GEOMETRY)
    mission=AutomaticMissionService(automatic);server=sim=bridge=child=controller=app_peer=None
    separated=args.remote_pipe and args.isaac
    result={'status':'FAIL','data':'OUTPUT_REACTIVE_SYNTHETIC_RAYCAST','robot_connections':0,'provider_calls':0,
        'physical_validation':'NOT_RUN','live_adapter':'NOT_CONFIGURED','isaac':'NOT_RUN','checks':[]}
    starts=iter(([0.,-.6,0.],[-.3,-.4,.25]));adapters=[]
    if args.remote_pipe and not separated:
        from twinpulse_app.physical_controller import PhysicalController
        from tests.fixtures.observed_robot_process import fixture_evidence_exporter
        controller=PhysicalController(state,command=lambda _r,_m:[sys.executable,'-B',str(ROOT/'tests/fixtures/observed_robot_process.py'),str(state/'peer')],evidence_exporter=fixture_evidence_exporter(state/'peer'))
        result['remote_pipe']='ACTUAL_LOCAL_SUBPROCESS_SYNTHETIC_ROS'
    if separated:
        result['remote_pipe']='ACTUAL_LOCAL_SUBPROCESS_SYNTHETIC_ROS'
        result['app_engine_processes']='SEPARATE_ACTUAL_APP_AND_ISAAC'
    def factory(prior,room,effective,goal):
        if args.remote_pipe:
            from twinpulse_app.remote_observed_adapter import RemoteObservedAdapter
            from twinpulse_core.adaptive_mission_contract import nominal_room
            scope={'schema':'observed-mission-scope-2.0','project_id':pid,'goal':goal,'reference':None,'alignment':None,
                   'nominal':nominal_room(effective['objects'],.182,effective['effective_revision'])}
            a=RemoteObservedAdapter(controller,lambda _:{},scope);adapters.append(a);return a
        from tests.integration.test_cold_start_mission import ColdAdapter
        a=(ColdAdapter if args.cold else RaycastAdapter)(prior,room,effective,goal,outline=outline,start=next(starts))
        if args.dense_scan:
            from packages.twinpulse_core.tests.test_room_localization import scan_points
            a.observation_points=lambda:scan_points(a.outline,a.world,beam_count=720)
        adapters.append(a);return a
    factory.supports_local_correction=True
    factory.supports_remote_correction=args.remote_pipe
    mission.adapter_factory=factory
    paths=[ROOT/p for p in ('packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
        'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
        'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
        'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
        'packages/twinpulse_core/src/twinpulse_core/room_localization.py',
        'packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
        'packages/twinpulse_core/src/twinpulse_core/active_mission_visual.py',
        'packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py',
        'packages/twinpulse_core/src/twinpulse_core/local_navigation.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_visual.py',
        'packages/twinpulse_app/src/twinpulse_app/mission_photo_correction.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_photo_store.py',
        'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py','packages/twinpulse_robot_safety/mission_runtime.py',
        'packages/twinpulse_robot_safety/teleop_ros.py','apps/twinpulse-web/src/AutomaticMission.tsx',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py',
        'apps/twinpulse-web/e2e/automatic-mission-real.mjs','scripts/verify_ad4_observed_mission.py',
        'packages/twinpulse_core/src/twinpulse_core/adaptive_mission_contract.py',
        'packages/twinpulse_core/src/twinpulse_core/mission_correction_contract.py',
        'packages/twinpulse_robot_safety/observed_runtime.py',
        'packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py',
        'packages/twinpulse_app/src/twinpulse_app/physical_controller.py',
        'packages/twinpulse_app/src/twinpulse_app/session_history.py',
        'scripts/robot_source_identity.py','tests/fixtures/observed_robot_process.py','scripts/ad4_remote_app_peer.py')]
    paths+=list(p for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file())
    if args.dense_scan:
        paths+=[ROOT/p for p in ('tests/integration/test_automatic_mission_service.py',
            'tests/integration/test_cold_start_mission.py','packages/twinpulse_core/tests/test_room_localization.py',
            'packages/twinpulse_core/tests/test_endpoint_field_score.py','tests/integration/test_dense_cold_navigation.py')]
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};result['source_sha256']=hashes
    try:
        outline,_=recipe(state,pid,1.,import_now=False)
        if args.remote_pipe:
            peer=state/'peer';peer.mkdir()
            (peer/'synthetic-world.json').write_text(json.dumps({'vertices':[a for a,_ in outline['segments']],'start':[0.,-.6,0.]}))
        prepare_project_burger_visual(state,pid,(0.,-.6,.002),0.)
        import_project_room_recipe(state,pid)
        map_id=None
        if not args.cold:
            automatic.start('preparation','a'*32,photo_policy='align_only');automatic.worker.join(20)
            prepared=automatic.snapshot('preparation')['job']
            if prepared['state']!='COMPLETED' or prepared['result']['photo_alignment']['status']!='ALIGNMENT_CANDIDATE':
                raise ValueError('PRIOR_PREPARATION_FAILED')
            map_id=prepared['map_id'];automatic.job=None # Isolated fixture, not a production ownership bypass.
        broker=CommandBroker(project_id=pid)
        app=ApplicationService(NoGateway(),project_store=ProjectStore.for_project(state,pid),project_id=pid)
        workflow=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
        original=app._project_store.path.read_bytes()
        if args.isaac:
            from isaacsim import SimulationApp
            sim=SimulationApp({'headless':True,'width':960,'height':720})
            import omni.usd,omni.timeline
            from pxr import UsdGeom
            from twinpulse.extension.runtime import TwinPulseRuntime
            from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
            from twinpulse.extension.bridge_client import BridgeClient
            omni.usd.get_context().new_stage()
            for _ in range(8):sim.update()
            stage=omni.usd.get_context().get_stage()
            UsdGeom.Xform.Define(stage,'/ExternalKeep').GetPrim().SetCustomDataByKey('marker','preserve')
            runtime=TwinPulseRuntime();engine=IsaacSimulationAdapter(runtime,project_id=pid,project_state_root=state)
        secret=secrets.token_urlsafe(32);engine_secret=secrets.token_urlsafe(32)
        if separated:
            executable=ROOT/'.venv/Scripts/python.exe'
            if not executable.is_file():raise ValueError('EXISTING_APP_PYTHON_REQUIRED')
            app_peer=subprocess.Popen([str(executable),'-B',str(ROOT/'scripts/ad4_remote_app_peer.py'),str(state),str(output)],
                cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            app_peer.stdin.write((json.dumps({'product_secret':secret,'engine_secret':engine_secret})+'\n').encode());app_peer.stdin.flush()
            startup=queue.Queue()
            def read_startup():startup.put(app_peer.stdout.readline())
            reader=threading.Thread(target=read_startup,daemon=True);reader.start()
            try:ready=json.loads(startup.get(timeout=15))
            except (queue.Empty,ValueError):raise ValueError('OFFLINE_APP_PEER_STARTUP_FAILED')
            if set(ready)!={'state','base_url'} or ready['state']!='OFFLINE_APP_READY' or not ready['base_url'].startswith('http://127.0.0.1:'):
                raise ValueError('OFFLINE_APP_PEER_IDENTITY')
            base_url=ready['base_url']
        else:
            server=LocalApiServer(broker,product_bootstrap_secret=secret,engine_bootstrap_secret=engine_secret,
                product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',session_history_root=state,
                credential_store=NoCredentials())
            server.automatic_mission.close();server.automatic_demo.close();server.automatic_demo=automatic;server.automatic_mission=mission
            server.start();base_url=server.base_url
        if args.isaac:bridge=BridgeClient(engine,base_url=base_url,bootstrap_secret=engine_secret);bridge.start()
        node=shutil.which('node');chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
        if not node or not chrome.is_file():raise ValueError('EXISTING_BROWSER_RUNTIME_REQUIRED')
        frames=[];seen=None;active_receipt_seen=False;active_geometry_seen=False
        environment=dict(os.environ,TWINPULSE_REHEARSAL_URL=base_url,TWINPULSE_REHEARSAL_BOOTSTRAP=secret,
            TWINPULSE_REHEARSAL_OUTPUT=str(output),TWINPULSE_REHEARSAL_CHROME=str(chrome),
            TWINPULSE_REHEARSAL_MAP=map_id or '',TWINPULSE_REHEARSAL_ISAAC='1' if args.isaac else '0',
            TWINPULSE_REHEARSAL_COLD='1' if args.cold else '0',
            TWINPULSE_REHEARSAL_DENSE='1' if args.dense_scan else '0',
            TWINPULSE_REHEARSAL_CORRECTION='1' if args.correct_walls else '0')
        child=subprocess.Popen([node,str(ROOT/'apps/twinpulse-web/e2e/automatic-mission-real.mjs')],
            cwd=ROOT/'apps/twinpulse-web',env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        # Failed browser diagnostics can exceed the Windows pipe capacity.
        # Drain while running, not after poll(): otherwise printing a failure
        # can block browser exit and hide the real cause behind a timeout.
        browser_io={'stdout':bytearray(),'stderr':bytearray()};browser_readers=[]
        def drain(stream,name):
            while True:
                block=stream.read(4096)
                if not block:break
                remaining=128*1024-len(browser_io[name])
                if remaining>0:browser_io[name].extend(block[:remaining])
        for name in ('stdout','stderr'):
            reader=threading.Thread(target=drain,args=(getattr(child,name),name),daemon=True)
            browser_readers.append(reader);reader.start()
        # Dense ray processing plus headless rendering is wall-time work in
        # this synthetic fixture. Do not renew its45 s source-clock mission.
        result['browser_wall_timeout_s']=210 if args.dense_scan else 150
        end=time.monotonic()+result['browser_wall_timeout_s']
        while child.poll() is None and time.monotonic()<end:
            if sim:
                sim.update();bridge.update();assert not omni.timeline.get_timeline_interface().is_playing()
                if not separated:
                    active_receipt_seen=active_receipt_seen or bool(mission.job and mission.worker.is_alive()
                        and mission.job.get('isaac_display',{}).get('status')=='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED')
                    active_geometry_seen=active_geometry_seen or bool(mission.job and mission.worker.is_alive()
                        and engine._mission_geometry_receipts and engine.mission_objects_revision()==mission.job['objects_revision'])
                cursor=engine._mission_visual_cursor
                if cursor and cursor!=seen:
                    from twinpulse.extension.bedroom_preview import PREVIEW_PATH
                    seen=cursor;marker=stage.GetPrimAtPath(PREVIEW_PATH)
                    frames.append({'job_id':cursor[0],'sequence':cursor[1],'position':list(marker.GetAttribute('xformOp:translate').Get()),
                                   'objects_revision':engine.mission_objects_revision(),'pose_status':marker.GetCustomDataByKey('poseStatus')})
                    if separated and frames[-1]['pose_status']=='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED':
                        active_receipt_seen=True
                        active_geometry_seen=active_geometry_seen or bool(engine._mission_geometry_receipts
                            and frames[-1]['objects_revision']==engine._mission_geometry_receipts[0]['objects_revision'])
            time.sleep(.005)
        if child.poll() is None:raise TimeoutError('OWNED_BROWSER_DEADLINE')
        for reader in browser_readers:reader.join(2)
        if any(reader.is_alive() for reader in browser_readers):raise ValueError('OWNED_BROWSER_OUTPUT_INCOMPLETE')
        stdout,stderr=bytes(browser_io['stdout']),bytes(browser_io['stderr'])
        result['browser_exit_code']=child.returncode
        for name,data in (('stdout',stdout),('stderr',stderr)):
            safe=data.decode('utf-8',errors='replace').replace(secret,'[REDACTED]').replace(engine_secret,'[REDACTED]')
            (output/f'browser-{name}.log').write_text(safe[:128*1024],encoding='utf-8')
        browser=json.loads((output/'browser-result.json').read_text(encoding='utf-8'));result['browser']=browser
        if child.returncode or browser['status']!='PASS':raise ValueError('BROWSER_ACCEPTANCE_FAILED')
        if separated:
            peer_stdout,peer_stderr=app_peer.communicate(input=b'{"action":"finish"}\n',timeout=20)
            (output/'app-peer-stderr.log').write_text(peer_stderr.decode('utf-8',errors='replace').replace(secret,'[REDACTED]').replace(engine_secret,'[REDACTED]')[:128*1024])
            if app_peer.returncode:raise ValueError('OFFLINE_APP_PEER_CAPTURE_FAILED')
            captured=json.loads((output/'remote-app-result.json').read_text(encoding='utf-8'))
            if captured['status']!='CAPTURED' or not captured['original_project_unchanged']:raise ValueError('OFFLINE_APP_PEER_RESULT')
            job=captured['job']
        else:job=mission.job
        descriptor={'kind':'automatic_mission_visual_v1','mission_id':job['job_id'],'manifest_sha256':job['report_revision']}
        _,_,_,scene,visual=checked_mission_visual(state,pid,descriptor)
        if args.correct_walls:
            from twinpulse_app.automatic_photo_store import load_automatic_room
            effective=automatic.photo_store.current(load_automatic_room(state,pid))
            assert len(effective['events'])==1
            assert job['goal']['room_revision']==effective['effective_revision']==job['visual']['room_revision']
            assert job['original_goal']['room_revision']!=job['goal']['room_revision']
            assert job['photo_correction']['goal_revalidation']=='NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED'
            result['photo_correction']=job['photo_correction']
            result['checks']+=['same_Start_idle_append_immutable_original_goal_and_fresh_rebound_plan',
                               'old_active_Isaac_geometry_never_used_for_current_pose']
        assert app._project_store.path.read_bytes()==original
        if not separated:assert len(adapters)==(1 if args.cold else 2)
        if args.remote_pipe:
            from twinpulse_app.session_history import review_session
            history=review_session(state,job['job_id']);peer_report=state/'artifacts/manual-control'/job['job_id']/'robot-report.json'
            final=json.loads(peer_report.read_text(encoding='utf-8'));current=captured['controller'] if separated else controller.snapshot(adapters[0].owner)
            assert not current['busy'] and current['cleanup_confirmed'] and current['sensor_cleanup_confirmed']
            assert final['synthetic_final_velocity']==[0.,0.] and final['physical_validation']=='SYNTHETIC_TEST_ONLY'
            assert {r['kind'] for r in history['correction_exchange']}=={'correction_proposal_received','correction_reply_sent','correction_robot_receipt'}
            assert job['photo_correction']['status']=='ROBOT_IDLE_BINDING_ACKNOWLEDGED'
            assert (captured['scope'] if separated else adapters[0].scope)['goal']==job['original_goal']
            for path in (peer_report,peer_report.parent/'session.jsonl',peer_report.parent/'result.json',state/'peer/published.json',state/'peer/synthetic-world.json'):
                shutil.copyfile(path,output/path.name)
            result['remote_artifact_sha256']={p.name:hashlib.sha256((output/p.name).read_bytes()).hexdigest() for p in
                (peer_report,peer_report.parent/'session.jsonl',peer_report.parent/'result.json',state/'peer/published.json',state/'peer/synthetic-world.json')}
            result['checks']+=['actual_remote_pc_pipe_bootstrap_idle_proposal_immutable_append_ack_and_fresh_sensor_goal']
        else:
            assert all(a.halted and a.velocity==(0.,0.) for a in adapters)
            # Success and failure both persist raw in finally after cleanup.
            if args.dense_scan:
                assert all(a.raw and all(len(r['ranges'])==720 for r in a.raw) for a in adapters)
                assert 0<len(visual['scan_room'])<=160
                result['dense_scan']={'raw_beams':720,'saved_display_beams':len(visual['scan_room']),
                    'actual_sensor_or_remote_validation':'NOT_RUN'}
                result['checks']+=['dense_original_rays_preserved_and_saved_visual_bounded']
        result['checks']+=['one_cold_start_no_prior' if args.cold else 'two_independent_starts_fresh_matching_no_old_pose',
            'built_Web_auth_API_actual_worker_feedback_not_injected_arrival','source_bound_saved_Twin_descriptor','project_original_unchanged']
        if sim:
            from twinpulse.extension.bedroom_preview import PREVIEW_PATH
            operation_statuses=captured['operation_statuses'] if separated else [o.status for o in broker._operations.values()]
            assert len(operation_statuses)==(2 if args.cold else 1)
            assert all(status=='succeeded' for status in operation_statuses)
            assert runtime.compiler.matches_site_scene(scene)
            marker=stage.GetPrimAtPath(PREVIEW_PATH)
            actual=marker.GetAttribute('xformOp:translate').Get()
            assert max(abs(actual[i]-visual['pose_room'][i]) for i in (0,1))<1e-6
            assert marker.GetCustomDataByKey('missionSessionId')==job['job_id']
            overlay=stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission')
            assert overlay.GetCustomDataByKey('revision')==visual['revision']
            if args.dense_scan:
                cloud=stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission/Scan')
                points=cloud.GetAttribute('points').Get()
                assert len(points)==len(visual['scan_room'])
                assert max(abs(points[i][j]-visual['scan_room'][i][j]) for i in range(len(points)) for j in (0,1))<1e-6
                result['dense_scan']['isaac_saved_points']=len(points)
            assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='preserve'
            assert not omni.timeline.get_timeline_interface().is_playing()
            result.update(isaac='SAVED_VISUAL_RUNTIME_PASS',scene_revision=scene.revision,visual_revision=visual['revision'])
            if args.correct_walls:
                assert active_receipt_seen and active_geometry_seen
                assert len(engine._mission_geometry_receipts)==1
                assert engine._mission_geometry_receipts[0]['objects_revision']==effective['effective_revision']
                assert job['photo_correction']['isaac_geometry_status']=='OWNED_ISAAC_GEOMETRY_COMPOSED'
                corrected_frames=[r for r in frames if r['objects_revision']==effective['effective_revision']
                                  and r['pose_status']=='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED']
                assert len(corrected_frames)>=3
                assert len({tuple(round(v,4) for v in r['position']) for r in corrected_frames})>=2
                result.update(isaac='COLD_CORRECTION_ACTIVE_AND_SAVED_VISUAL_RUNTIME_PASS',active_geometry='OWNED_RUNTIME_COMPOSED',
                              active_frames=frames,corrected_active_frame_count=len(corrected_frames),geometry_receipts=engine._mission_geometry_receipts)
                if args.remote_pipe:result['isaac']='REMOTE_CORRECTION_ACTIVE_AND_SAVED_VISUAL_RUNTIME_PASS'
                result['checks']+=['corrected_active_then_saved_room_actually_composed_via_auth_API_bridge_Isaac',
                                   'fresh_pose_requested_separately_after_geometry_composition']
            elif args.cold:
                assert len(frames)>=3 and len({tuple(round(v,4) for v in r['position']) for r in frames})>=2
                assert active_receipt_seen
                assert mission.job['map_id'] is None
                result.update(isaac='COLD_ACTIVE_AND_SAVED_VISUAL_RUNTIME_PASS',active_frames=frames)
                result['checks']+=['no_prior_cold_start_survey_fit_goal_in_one_browser_Start','active_Isaac_poses_via_authenticated_API_and_Bridge']
            stage.GetRootLayer().Export(str(output/'mission-stage.usda'))
        if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p.relative_to(ROOT))] for p in paths):
            raise ValueError('SOURCE_OR_BUILD_CHANGED')
        result['status']='PASS'
    except Exception as exc:result.update(error_type=type(exc).__name__,reason=str(exc)[:180])
    finally:
        if child is not None and child.poll() is None:child.terminate();child.wait(timeout=10)
        if bridge:bridge.stop()
        if app_peer:
            if app_peer.poll() is None:app_peer.terminate()
            try:
                _,errors=app_peer.communicate(timeout=10)
                if errors:(output/'app-peer-stderr.log').write_text(errors.decode('utf-8',errors='replace').replace(secret,'[REDACTED]').replace(engine_secret,'[REDACTED]')[:128*1024])
            except (ValueError,subprocess.TimeoutExpired):result['app_peer_cleanup']='OWNED_CHILD_CLEANUP_UNCONFIRMED'
        if server:server.stop()
        else:mission.close();automatic.close()
        if controller:controller.close()
        # Save after owned-worker cleanup, including failed runs. A browser
        # timeout must not discard the only raw fixture evidence. If cleanup
        # is incomplete, explicitly mark the capture as a prefix, not full raw.
        if not args.remote_pipe:
            complete=not (mission.worker and mission.worker.is_alive())
            result['synthetic_raw_complete']=complete
            for index,a in enumerate(adapters):
                path=output/f'synthetic-raw-{index}.json'
                if not path.exists():
                    path.write_text(json.dumps({'provenance':'synthetic_raycast','physical_validation':'NOT_RUN',
                        'complete':complete,'observations':a.raw,'commands':a.sent},allow_nan=False),encoding='utf-8')
            result['synthetic_raw_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.glob('synthetic-raw-*.json')}
        (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:result.get(k) for k in ('status','isaac','reason','robot_connections','physical_validation')}),flush=True)
        if sim:sim.close()
    print(json.dumps({k:result.get(k) for k in ('status','isaac','reason','robot_connections','physical_validation')}))
    return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
