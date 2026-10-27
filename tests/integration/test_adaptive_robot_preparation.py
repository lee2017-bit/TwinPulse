# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Prepared release + actual pipe/robot loop, no robot/ROS/serial/SSH."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[2]
for folder in (ROOT/'scripts',ROOT/'packages/twinpulse_robot_safety',ROOT/'packages/twinpulse_core/src',ROOT/'packages/twinpulse_app/src',ROOT/'packages/twinpulse_provider/src'):
    sys.path.insert(0,str(folder))  # importable with -m unittest from the repo root, like the other robot-path modules
from robot_source_identity import bundle_files
from twinpulse_core.adaptive_mission_contract import adaptive_scope,adaptive_bootstrap
from twinpulse_core.mission_contract import document_hash
from twinpulse_core.revisions import canonical_sha256
from twinpulse_app.physical_controller import PhysicalController
from twinpulse_app.remote_observed_adapter import RemoteObservedAdapter,checked_remote_visual
from twinpulse_app.session_history import review_session
from mission_runtime import validate_request
from twinpulse_core.navigation_binding import PlanarBinding
from tests.fixtures.observed_robot_process import fixture_evidence_exporter


def scope():
    return {'schema':'observed-mission-scope-1.0','project_id':'test_room',
        'goal':{'mode':'SURVEY_LOCAL','xy':[.18,0.],'room_revision':'f'*64,'duration_s':15.},
        'reference':None,'alignment':None}


class PreparedRobotTests(unittest.TestCase):
    def save_pipe_fixture_evidence(self,root,fake,scope,case):
        """Opt-in immutable test receipt; cannot create physical qualification."""
        name=os.environ.get('TWINPULSE_TEST_PIPE_EVIDENCE_NAME')
        if not name:return
        import re
        self.assertRegex(name,r'^[a-z0-9-]{1,100}$')
        destination=ROOT/'artifacts'/name/case
        destination.mkdir(parents=True,exist_ok=False)
        source=root/'artifacts/manual-control'/('e'*32)
        files={p.name:p.read_bytes() for p in source.iterdir() if p.is_file() and p.name in {'robot-report.json','session.jsonl'}}
        files['published.json']=(fake/'published.json').read_bytes()
        files['scope.json']=json.dumps(scope,sort_keys=True).encode()
        for name,data in files.items():(destination/name).write_bytes(data)
        sources=('tests/integration/test_adaptive_robot_preparation.py','tests/fixtures/observed_robot_process.py',
                 'packages/twinpulse_app/src/twinpulse_app/physical_controller.py',
                 'packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py',
                 'packages/twinpulse_robot_safety/mission_runtime.py','packages/twinpulse_robot_safety/observed_runtime.py',
                 'packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
                 'packages/twinpulse_core/src/twinpulse_core/observation_stream.py')
        proof={'schema':'test-only-cold-pipe-receipt-1.0','status':'PASS','case':case,
               'physical_validation':'NOT_RUN','sensor_basis':'OUTPUT_REACTIVE_SYNTHETIC_ROS_MESSAGES',
               'robot_connections':0,'provider_calls':0,'motion_authorized':False,
               'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
               'artifact_sha256':{p:hashlib.sha256(data).hexdigest() for p,data in files.items()}}
        (destination/'verification.json').write_text(json.dumps(proof,sort_keys=True,indent=2))

    def test_cold_diagnostics_old_and_extended_shapes_keep_safe_exact_cause(self):
        from twinpulse_app.physical_controller import valid_event
        data={'stage':'ALIGN','view_count':17,'map_revision':'a'*64,'alignment_status':'NOT_RUN',
              'alignment_revision':None,'reason':'PHOTO_SOURCE_REVISION_CHANGED'}
        event={'schema':'robot-session-1.0','robot_session_id':'synthetic','event_index':1,
               'clock_domain':'robot_monotonic','t':1.,'kind':'cold_start_diagnostics','data':data}
        self.assertTrue(valid_event(event,adaptive=True));self.assertFalse(valid_event(event,adaptive=False))
        for extra in ({'error_stage':None,'error_type':None},{'error_stage':'PHOTO_ALIGNMENT','error_type':'ValueError'}):
            self.assertTrue(valid_event({**event,'data':{**data,**extra}},adaptive=True))
        for extra in ({'error_stage':'PHOTO_ALIGNMENT'}, {'error_stage':'OTHER','error_type':'ValueError'},
                      {'error_stage':None,'error_type':'ValueError'},
                      {'error_stage':'PHOTO_ALIGNMENT','error_type':'credential=SECRET'}, {'approved':True}):
            with self.subTest(extra=extra):self.assertFalse(valid_event({**event,'data':{**data,**extra}},adaptive=True))

    def test_robot_cleanup_requires_both_motor_and_owned_sensor_confirmation(self):
        for key,code in (('cleanup_confirmed','OBSERVED_ROBOT_CLEANUP_NOT_CONFIRMED'),
                         ('sensor_cleanup_confirmed','OBSERVED_SENSOR_CLEANUP_NOT_CONFIRMED')):
            with self.subTest(key=key),TemporaryDirectory() as td:
                controller=PhysicalController(td)
                state={'busy':False,'result':'MISSION_ARRIVED','reason':None,
                       'cleanup_confirmed':True,'sensor_cleanup_confirmed':True}
                state[key]=False
                controller.start=lambda *_a,**_k: None
                controller.snapshot=lambda _: dict(state)
                adapter=RemoteObservedAdapter(controller,lambda _: {},scope())
                with self.assertRaisesRegex(ValueError,code):
                    adapter.run(record=lambda *_a,**_k: None,visual=lambda _: None,safety=lambda: None)
                adapter.close();controller.close()

    def test_preflight_collects_all_independent_missing_gates_without_robot(self):
        from run_robot_field_suite import inspect_adaptive_preparation
        value=inspect_adaptive_preparation(ROOT)
        self.assertFalse(value['robot_contacted']);self.assertFalse(value['motion_authorized'])
        self.assertEqual(value['status'],'NOT_READY_BEFORE_ROBOT_CONNECTION')
        self.assertEqual(value['checks']['deployable_source']['status'],'PASS_LOCAL_ONLY')
        self.assertEqual(len(value['checks']),6)
        self.assertEqual(value['checks']['autonomous_profile']['reason'],'AUTONOMOUS_PROFILE_NOT_REVIEWED')
        self.assertEqual(value['checks']['reviewed_release_registration']['reason'],'REVIEWED_OBSERVED_RELEASE_NOT_REGISTERED')
        with self.assertRaises(ValueError):inspect_adaptive_preparation(ROOT,'../outside')

    def test_actual_service_fresh_survey_without_saved_map_and_owner_disconnect_cleanup(self):
        from twinpulse_app.automatic_demo_service import AutomaticDemoService
        from twinpulse_app.automatic_mission_service import AutomaticMissionService
        from tests.integration.test_automatic_photo_service import recipe
        from tests.integration.test_automatic_demo_service import GEOMETRY
        for disconnect in (False,True):
            with self.subTest(disconnect=disconnect),TemporaryDirectory() as td:
                root=Path(td);recipe(root,'test_room',1.);fake=root/'fake';fake.mkdir()
                controller=PhysicalController(root,command=lambda _r,_m:[sys.executable,'-B',str(ROOT/'tests/fixtures/observed_robot_process.py'),str(fake)],evidence_exporter=fixture_evidence_exporter(fake))
                automatic=AutomaticDemoService(root,'test_room',geometry_loader=lambda:GEOMETRY)
                adapters=[]
                def factory(prior,room,effective,goal):
                    self.assertIsNone(prior['map']['revision'])
                    value=scope();value['goal']=goal
                    adapter=RemoteObservedAdapter(controller,lambda _: {},value);adapters.append(adapter);return adapter
                service=AutomaticMissionService(automatic,adapter_factory=factory)
                try:
                    revision=service.readiness(None)['room_revision']
                    goal={**scope()['goal'],'room_revision':revision}
                    started=service.start('browser',None,goal)['job'];deadline=time.monotonic()+25
                    while service.worker.is_alive() and time.monotonic()<deadline:
                        if not disconnect:service.snapshot('browser')
                        service.worker.join(.05)
                    self.assertFalse(service.worker.is_alive())
                    job=service.snapshot('browser')['job']
                    self.assertEqual(job['state'],'FAILED' if disconnect else 'MISSION_ARRIVED',job)
                    if disconnect:self.assertEqual(job['error'],'MISSION_OWNER_CONNECTION_LOST')
                    else:self.assertTrue(job['result']['sensor_cleanup_confirmed'])
                    report=json.loads((root/'artifacts/automatic-mission/test_room'/f"{started['job_id']}.json").read_text())
                    self.assertEqual(report['physical_validation'],'NOT_RUN')
                    self.assertFalse(controller.snapshot(adapters[0].owner)['busy'])
                    self.assertTrue(controller.snapshot(adapters[0].owner)['cleanup_confirmed'])
                finally:service.close();automatic.close();controller.close()

    def test_deployable_archive_imports_without_desktop_or_ros_and_same_type_identity(self):
        members=bundle_files(ROOT)
        with TemporaryDirectory() as td:
            base=Path(td)
            for name,data in members.items():
                if name.endswith('.py'):
                    compile(data,name,'exec')
                    path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            code='import sys;sys.path.insert(0,sys.argv[1]);import mission_runtime,teleop_ros,observed_runtime;from twinpulse_core.navigation_binding import PlanarBinding;assert mission_runtime.PlanarBinding is PlanarBinding;from twinpulse_core.automatic_mapping import AutomaticMapping;from twinpulse_core.automatic_photo_alignment import align_photo_map;assert "rclpy" not in sys.modules;print("DEPLOYABLE_IMPORT_PASS")'
            result=subprocess.run([sys.executable,'-I','-B','-c',code,td],cwd=td,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('DEPLOYABLE_IMPORT_PASS',result.stdout)
        for name in ('observed_mission.py','current_mission_evidence.py','adaptive_mission_contract.py'):
            self.assertEqual(members['twinpulse_core/'+name],(ROOT/'packages/twinpulse_core/src/twinpulse_core'/name).read_bytes())

    def test_nonce_robot_clock_goal_bounds_no_photo_promotion_or_scope_mutation(self):
        context={'state':'MISSION_CONTEXT','boot_id':'test','release_id':'a'*64,'calibration_sha256':'b'*64,'issued_s':20.,'nonce':'c'*24}
        original=scope();packet=adaptive_bootstrap(context,'d'*32,original);original['goal']['xy'][0]=9
        self.assertEqual(packet['request']['adaptive_scope']['goal']['xy'],[.18,0.])
        binding=PlanarBinding('base_footprint','base_scan',(0.,0.,0.),(.1,0.,0.),.18,'e'*64)
        request=packet['request'];checked=validate_request(request,document_hash(request),binding,'b'*64,{'source_id':'a'*64},'test',20.1)
        self.assertEqual(checked['adaptive_scope']['goal']['room_revision'],'f'*64)
        for field,value in (('boot_id','other'),('scope_sha256','0'*64),('duration_s',46),('expires_s',20.)):
            with self.subTest(field=field),self.assertRaises(ValueError):validate_request({**request,field:value},'e'*64,binding,'b'*64,{'source_id':'a'*64},'test',20.1)
        for fault in ({'reference':{}},{'goal':{**scope()['goal'],'xy':[.51,0.]}},{'goal':{**scope()['goal'],'duration_s':True}},{'approved':True}):
            with self.assertRaises(ValueError):adaptive_scope({**scope(),**fault})

    def test_default_registration_is_rejected_without_starting_a_child(self):
        from twinpulse_app.observed_release_registration import ObservedReleaseRegistration
        with TemporaryDirectory() as td:
            calls=[];controller=PhysicalController(td,factory=lambda *a,**k:calls.append(a))
            adapter=RemoteObservedAdapter(controller,ObservedReleaseRegistration(td,'test_room','f'*64),scope())
            with self.assertRaisesRegex(ValueError,'NOT_REGISTERED'):adapter.admit(scope()['goal'])
            self.assertFalse(calls);self.assertFalse(adapter.started);controller.close()

    def test_actual_pc_pipe_bootstrap_robot_observed_loop_sensor_feedback_and_archive(self):
        with TemporaryDirectory() as td:
            root=Path(td);fake=root/'fake';fake.mkdir()
            controller=PhysicalController(root,command=lambda _r,_m:[sys.executable,'-B',str(ROOT/'tests/fixtures/observed_robot_process.py'),str(fake)],evidence_exporter=fixture_evidence_exporter(fake))
            adapter=RemoteObservedAdapter(controller,lambda value:{},scope())
            adapter.admit(scope()['goal']);adapter.bind_session('d'*32);events=[];visuals=[]
            try:
                try:result=adapter.run(record=lambda kind,**data:events.append((kind,data)),visual=visuals.append,safety=lambda:None)
                except ValueError as exc:
                    report=root/'artifacts/manual-control'/('d'*32)/'robot-report.json'
                    self.fail(str(exc)+' '+report.read_text() if report.is_file() else str(exc))
                self.assertEqual(result['status'],'MISSION_ARRIVED');self.assertTrue(result['sensor_cleanup_confirmed'])
                self.assertTrue(any(k=='published' for k,_ in events));self.assertTrue(visuals)
                self.assertEqual(visuals[-1]['session_id'],'d'*32);self.assertIsNone(visuals[-1]['pose_room'])
                final=json.loads((root/'artifacts/manual-control'/('d'*32)/'robot-report.json').read_text())
                self.assertGreater(final['synthetic_final_pose'][0],.04)
                self.assertEqual(final['physical_validation'],'SYNTHETIC_TEST_ONLY')
                history=review_session(root,'d'*32);self.assertEqual(history['project_id'],'test_room')
                self.assertGreater(history['published_count'],2);self.assertFalse(history['motion_authorized'])
                self.assertNotIn('challenge',(root/'artifacts/manual-control'/('d'*32)/'session.jsonl').read_text())
            finally:adapter.close();controller.close()

    def test_cold_v2_actual_pc_pipe_survey_fit_goal_and_raw_diagnostics(self):
        from twinpulse_core.adaptive_mission_contract import nominal_room
        from tests.integration.test_automatic_photo_service import recipe
        with TemporaryDirectory() as td:
            root=Path(td);fake=root/'fake';fake.mkdir()
            outline,objects=recipe(root,'test_room',1.)
            # Independently retained raycaster geometry, never an injected
            # alignment, arrival state or estimator truth pose.
            world={'vertices':[a for a,_ in outline['segments']],'start':[0.,-.6,0.]}
            (fake/'synthetic-world.json').write_text(json.dumps(world))
            value={'schema':'observed-mission-scope-2.0','project_id':'test_room',
                'goal':{'mode':'SURVEY_THEN_NAVIGATE','xy':[.15,-.6],'room_revision':'f'*64,'duration_s':45.},
                'reference':None,'alignment':None,'nominal':nominal_room(objects,.182,'f'*64)}
            original=copy.deepcopy(value)
            controller=PhysicalController(root,command=lambda _r,_m:[sys.executable,'-B',str(ROOT/'tests/fixtures/observed_robot_process.py'),str(fake)],evidence_exporter=fixture_evidence_exporter(fake))
            adapter=RemoteObservedAdapter(controller,lambda _:{},value)
            adapter.admit(value['goal']);adapter.bind_session('e'*32);events=[];visuals=[]
            try:
                result=adapter.run(record=lambda kind,**data:events.append((kind,data)),visual=visuals.append,safety=lambda:None)
                self.assertEqual(result['status'],'MISSION_ARRIVED',result)
                self.assertTrue(result['sensor_cleanup_confirmed']);self.assertEqual(value,original)
                self.assertEqual(adapter.scope,original)
                diagnostic=next(data for kind,data in events if kind=='cold_start_diagnostics')
                self.assertEqual(diagnostic['stage'],'NAVIGATE');self.assertEqual(diagnostic['alignment_status'],'ALIGNMENT_CANDIDATE')
                self.assertIsNone(diagnostic['error_stage']);self.assertIsNone(diagnostic['error_type'])
                self.assertGreaterEqual(diagnostic['view_count'],8)
                reasons={data['decision']['reason'] for kind,data in events if kind=='mission_decision'}
                self.assertTrue({'SURVEY_RETURN_FOR_HELD_OUT_VIEWS','PHOTO_FIT_WHEELS_IDLE','PHOTO_CANDIDATE_RECHECK_CURRENT_SENSOR'}<=reasons)
                self.assertTrue(any(v['pose_room'] is not None for v in visuals))
                report=root/'artifacts/manual-control'/('e'*32)/'robot-report.json'
                final=json.loads(report.read_text())
                self.assertLess(math.dist(final['synthetic_final_pose'][:2],value['goal']['xy']),.10)
                self.assertTrue(final['cleanup_confirmed']);self.assertEqual(final['physical_validation'],'SYNTHETIC_TEST_ONLY')
                history=review_session(root,'e'*32)
                self.assertFalse(history['motion_authorized']);self.assertGreater(history['published_count'],2)
                journal=(report.parent/'session.jsonl').read_text()
                self.assertIn('cold_start_view',journal);self.assertIn('cold_start_diagnostics',journal)
                self.assertNotIn('challenge',journal)
                self.assertTrue((fake/('consumed-'+'e'*32)).is_file())
                self.assertEqual(final['synthetic_final_velocity'],[0.,0.])
                self.save_pipe_fixture_evidence(root,fake,value,'arrived')
            finally:adapter.close();controller.close()

    def test_cold_v2_remote_source_loss_and_stop_during_fit_never_resume(self):
        from twinpulse_core.adaptive_mission_contract import nominal_room
        from tests.integration.test_automatic_photo_service import recipe
        for fault in ('stale_scan','stop_at_fit'):
            with self.subTest(fault=fault),TemporaryDirectory() as td:
                root=Path(td);fake=root/'fake';fake.mkdir();outline,objects=recipe(root,'test_room',1.)
                world={'vertices':[a for a,_ in outline['segments']],'start':[0.,-.6,0.],'fault':fault}
                # The fit must still be running when the Stop arrives, or this is
                # a stop-during-NAVIGATE test. The fixture holds the fit (up to 5 s)
                # until the robot cancels, then lets the real fit finish late.
                if fault=='stop_at_fit':world['hold_fit_until_stop_s']=5.
                (fake/'synthetic-world.json').write_text(json.dumps(world))
                value={'schema':'observed-mission-scope-2.0','project_id':'test_room',
                    'goal':{'mode':'SURVEY_THEN_NAVIGATE','xy':[.15,-.6],'room_revision':'f'*64,'duration_s':45.},
                    'reference':None,'alignment':None,'nominal':nominal_room(objects,.182,'f'*64)}
                controller=PhysicalController(root,command=lambda _r,_m:[sys.executable,'-B',str(ROOT/'tests/fixtures/observed_robot_process.py'),str(fake)],evidence_exporter=fixture_evidence_exporter(fake))
                adapter=RemoteObservedAdapter(controller,lambda _:{},value);adapter.bind_session('e'*32)
                events=[]
                def record(kind,**data):
                    events.append((kind,data))
                    if fault=='stop_at_fit' and kind=='mission_decision' and data['decision']['reason']=='PHOTO_FIT_WHEELS_IDLE':
                        adapter.stop_requested=lambda:'force_stop'
                try:
                    if fault=='stale_scan':
                        # Continuing odom with a frozen scan violates the100 ms
                        # cross-sensor skew guard before the200 ms scan deadline.
                        with self.assertRaisesRegex(ValueError,'^NAVIGATION_TIME_SKEW$'):
                            adapter.run(record=record,visual=lambda _:None,safety=lambda:None)
                    else:
                        result=adapter.run(record=record,visual=lambda _:None,safety=lambda:None)
                        self.assertEqual(result['status'],'FORCE_STOPPED')
                    final=json.loads((root/'artifacts/manual-control'/('e'*32)/'robot-report.json').read_text())
                    self.assertNotEqual(final['status'],'MISSION_ARRIVED');self.assertEqual(final['synthetic_final_velocity'],[0.,0.])
                    self.assertTrue(final['cleanup_confirmed']);self.assertTrue(final['sensor_cleanup_confirmed'])
                    diagnostic=next(data for kind,data in events if kind=='cold_start_diagnostics')
                    self.assertNotEqual(diagnostic['stage'],'NAVIGATE')
                    if fault=='stop_at_fit':
                        self.assertEqual(diagnostic['stage'],'ALIGN')
                        stopped=next(i for i,(kind,_) in enumerate(events) if kind=='stop_requested')
                        self.assertFalse(any(kind=='published' for kind,_ in events[stopped+1:]))
                        # The Stop was received during the fit, nothing moved after it,
                        # and the late fit result was never consumed (never resumes).
                        self.assertTrue(final['synthetic_fit_held_until_cancelled'])
                        self.assertEqual(final['status'],'FORCE_STOPPED');self.assertEqual(final['synthetic_nonzero_after_stop'],0)
                        self.assertEqual(diagnostic['alignment_status'],'NOT_RUN')
                    self.assertFalse(controller.snapshot(adapter.owner)['busy'])
                    self.save_pipe_fixture_evidence(root,fake,value,fault)
                finally:adapter.close();controller.close()

    def test_visual_cannot_change_goal_epoch_geometry_or_authority(self):
        value={'schema':'automatic-mission-visual-1.0','session_id':'d'*32,
            'context':{'project_id':'test_room','session_id':'s','boot_id':'test','release_id':'a'*64,'source_revision':'a'*64,'origin':'live_ros'},
            'state':'SURVEYING','room_revision':'f'*64,'route_revision':None,'map_revision':None,'alignment_revision':None,
            'pose_room':None,'goal_room':None,'route_room':[],'scan_room':[],'trajectory_room':[[0.,0.,.1]],
            'motion_authorized':False,'physical_demo_ready':False,'provenance':'live_sensor'}
        value['revision']=canonical_sha256(value)
        checked_remote_visual(value,'d'*32,scope(),{'boot_id':'test','release_id':'a'*64})
        for key,bad in (('motion_authorized',True),('session_id','e'*32),('goal_room',[0.,0.]),('scan_room',[[float('nan'),0.]]),('revision','a'*64)):
            altered=copy.deepcopy(value);altered[key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):checked_remote_visual(altered,'d'*32,scope())


if __name__=='__main__':unittest.main()
