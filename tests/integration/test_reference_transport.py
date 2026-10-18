# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Full reference transfer and actual PC/native idle subprocess path, OFF only."""
from copy import deepcopy
from collections import deque
import base64
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import threading
import unittest
from unittest.mock import patch
from twinpulse_core.reference_transport import *
from twinpulse_core.adaptive_mission_contract import adaptive_scope,adaptive_bootstrap
from twinpulse_app.remote_observed_adapter import RemoteObservedFactory
from twinpulse_app.physical_controller import PhysicalController
from tests.integration.test_survey_reference import SurveyReferenceTests

ROOT=Path(__file__).resolve().parents[2]


class ReferenceWireTests(unittest.TestCase):
    def test_rejected_observation_retains_raw_and_distinct_transport_context_commit_diagnosis(self):
        for fault in ('transport','context','commit'):
            with self.subTest(fault=fault):
                context={'project_id':'p','session_id':'robot','boot_id':'boot',
                         'release_id':'a'*64,'source_revision':'a'*64,'origin':'live_ros'}
                evidence={**context,'sample_s':10.,'motion_authorized':False,'physical_demo_ready':False,
                    'alignment_revision':'b'*64,'room_from_map':[0.,0.,0.]}
                if fault=='context':evidence['project_id']='other'
                now=[10.21 if fault=='transport' else 10.05]
                controller=PhysicalController(ROOT,clock=lambda:now[0])
                controller.mode='localize';controller.job='job';controller.stop_requested=False
                controller.localization_query={'id':'c'*32,'started_s':10.}
                controller.localization_observation=None;controller.localization_received=None
                controller.localization_records=[];controller.localization_bytes=0
                controller.mission_context=context
                controller.mission_scope={'project_id':'p','alignment':{
                    'report_revision':'b'*64,'room_from_map':[0.,0.,0.]},'goal':{'room_revision':'d'*64}}
                rows=[];controller._record=lambda kind,**data:rows.append((kind,data))
                def binding(*args):
                    if fault=='commit':now[0]=10.25
                with patch('twinpulse_core.current_goal_preview.current_binding',side_effect=binding):
                    with self.assertRaisesRegex(ValueError,'EVIDENCE_STALE' if fault=='commit' else 'SOURCE_OR_TRANSPORT'):
                        controller._receive_localization(observation_packet('c'*32,evidence,10.),'robot')
                diagnostic=next(data for kind,data in rows if kind=='localization_validation_rejected')
                self.assertEqual(diagnostic['query_id'],'c'*32)
                if fault=='commit':self.assertGreaterEqual(diagnostic['evidence_age_upper_s'],.2)
                else:
                    self.assertEqual(diagnostic['transport_time_valid'],fault!='transport')
                    self.assertEqual(diagnostic['context_valid'],fault!='context')
                self.assertEqual(len(controller.localization_records),1)
                self.assertIsNone(controller.localization_observation);self.assertIsNone(controller.localization_received)

    def test_observation_validation_does_not_hold_input_lock_or_resurrect_after_stop(self):
        from types import SimpleNamespace
        context={'project_id':'p','session_id':'robot','boot_id':'boot',
                 'release_id':'a'*64,'source_revision':'a'*64,'origin':'live_ros'}
        evidence={**context,'sample_s':10.,'motion_authorized':False,'physical_demo_ready':False,
                  'alignment_revision':'b'*64,'room_from_map':[0.,0.,0.]}
        controller=PhysicalController(ROOT,clock=lambda:10.05)
        controller.mode='localize';controller.job='job';controller.stop_requested=False
        controller.localization_query={'id':'c'*32,'started_s':10.}
        controller.localization_observation=None;controller.localization_received=None
        controller.localization_records=[];controller.localization_bytes=0
        controller.mission_context=context
        controller.mission_scope={'project_id':'p','alignment':{
            'report_revision':'b'*64,'room_from_map':[0.,0.,0.]},'goal':{'room_revision':'d'*64}}
        controller._record=lambda *args,**kwargs:None
        entered=threading.Event();release=threading.Event();errors=[]
        def slow_decode(*args):
            entered.set();self.assertTrue(release.wait(2.));return evidence
        def receive():
            try:controller._receive_localization(observation_packet('c'*32,evidence,10.),'robot')
            except Exception as exc:errors.append(exc)
        with patch('twinpulse_core.reference_transport.checked_observation',side_effect=slow_decode),\
                patch('twinpulse_core.current_goal_preview.current_binding'):
            thread=threading.Thread(target=receive);thread.start()
            try:
                self.assertTrue(entered.wait(2.))
                self.assertTrue(controller.lock.acquire(timeout=.1))
                try:controller.stop_requested=True
                finally:controller.lock.release()
            finally:release.set();thread.join(2.)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertIsNone(controller.localization_observation)
        self.assertIsNone(controller.localization_received)
        self.assertEqual(len(controller.localization_records),1)  # Raw remains available.

    def test_full_chunk_roundtrip_no_downsample_and_duplicate_or_tamper_rejected(self):
        value={'points':[[i/1000.,i/2000.] for i in range(18000)]}
        sender=ReferenceSender(value);receiver=ReferenceReceiver(sender.descriptor,'a'*24)
        self.assertGreater(sender.descriptor['bytes'],16384)
        while not receiver.done:
            packet=sender.chunk('a'*24,receiver.index)
            self.assertLess(len(encode(packet,16384)),16384)
            result=receiver.accept(packet)
        self.assertEqual(result,value)
        with self.assertRaisesRegex(ValueError,'SEQUENCE'):receiver.accept(packet)
        for fault in ('nonce','index','length','hash'):
            with self.subTest(fault=fault):
                sender=ReferenceSender({'data':'x'*6500});receiver=ReferenceReceiver(sender.descriptor,'b'*24)
                packet=sender.chunk('b'*24,0)
                if fault=='nonce':packet['nonce']='c'*24
                if fault=='index':packet['index']=True
                if fault=='length':packet['data']='YQ=='
                if fault=='hash':packet['data']=base64.b64encode(b'y'*CHUNK).decode()
                with self.assertRaises(ValueError):
                    receiver.accept(packet)
                    if fault=='hash':receiver.accept(sender.chunk('b'*24,1))

    def test_size_json_and_observation_compression_preserve_all_rows(self):
        value={'cells':[[i,0,'free',10,'f'*64] for i in range(18000)]}
        packet=observation_packet('a'*32,value,10.)
        self.assertGreater(len(json.dumps(packet).encode()),60000)
        self.assertEqual(checked_observation(packet,'a'*32),value)
        sender=ReferenceSender(packet,chunk_size=OBSERVATION_CHUNK)
        receiver=ReferenceReceiver(sender.descriptor,'a'*24,chunk_size=OBSERVATION_CHUNK)
        while not receiver.done:
            chunk=sender.chunk('a'*24,receiver.index)
            self.assertLess(len(encode({'state':'LOCALIZATION_CHUNK','query_id':'a'*32,'chunk':chunk},65536)),65536)
            reassembled=receiver.accept(chunk)
        self.assertEqual(reassembled,packet)
        for fault in ('query','hash','bytes','packed','extra'):
            bad=deepcopy(packet)
            if fault=='query':bad['query_id']='b'*32
            if fault=='hash':bad['payload']['sha256']='b'*64
            if fault=='bytes':bad['payload']['bytes']=1
            if fault=='packed':bad['data']='bad!'
            if fault=='extra':bad['data']+=base64.b64encode(b'junk').decode()
            with self.subTest(fault=fault),self.assertRaises(ValueError):checked_observation(bad,'a'*32)
        with self.assertRaises(ValueError):ReferenceSender({'data':'x'*(MAX_REFERENCE+1)})
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):decode(b'{"a":1,"a":2}',50)
        with self.assertRaisesRegex(ValueError,'NONFINITE'):decode(b'{"a":NaN}',50)


class RemoteIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture=SurveyReferenceTests('test_full_reference_reopen_moved_start_and_actual_shared_loop')
        cls.capture.setUp()
        try:
            cls.report,cls.adapter=cls.capture.capture()
            cls.prior=cls.capture.load()
        except Exception:
            cls.capture.doCleanups();raise

    @classmethod
    def tearDownClass(cls):cls.capture.doCleanups()

    def scope(self):
        sender=ReferenceSender(self.prior)
        return adaptive_scope({'schema':'observed-mission-scope-6.0','phase':'IDLE_LOCALIZATION_ONLY',
            'project_id':'reference_room','goal':{'mode':'NAVIGATE_TWIN_GOAL','xy':[0.,0.],
                'room_revision':self.report['goal']['room_revision'],'duration_s':45.},
            'reference':{'kind':self.prior['reference_kind'],'revision':self.prior['map']['revision'],'payload':sender.descriptor},
            'alignment':{k:self.prior['photo_alignment'][k] for k in ('status','room_from_map','report_revision')}})

    def test_real_bootstrap_parser_full_reference_before_devices_and_cancel(self):
        from tests.fixtures.manual_robot_process import mission_fixture
        from mission_runtime import receive_request
        from twinpulse_core.navigation_binding import PlanarBinding
        scope=self.scope();sender=ReferenceSender(self.prior);packets=deque()
        class Incoming:
            def receive(self):return packets.popleft() if packets else None
        def output(value):
            if value['state']=='MISSION_CONTEXT':packets.append(adaptive_bootstrap(value,'a'*32,scope))
            elif value['state']=='REFERENCE_NEXT':packets.append(sender.chunk(value['nonce'],value['index']))
        binding=PlanarBinding('base_footprint','base_scan',(0.,0.,0.),(.1,0.,0.),.18,'a'*64)
        with patch('mission_runtime.load_calibration',return_value=(binding,'d'*64)):
            request=receive_request(None,{'source_id':'c'*64},'fake-boot',Incoming(),output,clock=lambda:10.)
        self.assertEqual(request['full_reference'],self.prior)
        self.assertEqual(checked_reference(self.prior,scope),self.prior)
        packets.clear()
        def cancelled(value):
            if value['state']=='MISSION_CONTEXT':packets.append(adaptive_bootstrap(value,'a'*32,scope))
            else:packets.append({'action':'force_stop'})
        with patch('mission_runtime.load_calibration',return_value=(binding,'d'*64)),self.assertRaisesRegex(ValueError,'CANCELLED'):
            receive_request(None,{'source_id':'c'*64},'fake-boot',Incoming(),cancelled,clock=lambda:10.)
        for field in ('phase','goal'):
            bad=deepcopy(scope)
            if field=='phase':bad[field]='EXECUTE'
            else:bad['goal']['xy']=[.1,0.]
            with self.assertRaises(ValueError):adaptive_scope(bad)
        bad={**scope,'goal':{**scope['goal'],'mode':'SURVEY_LOCAL'},'reference':None,'alignment':None}
        with self.assertRaisesRegex(ValueError,'IDLE_REFERENCE_SCOPE'):adaptive_scope(bad)

    def execute(self,delay=0.,large=False):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name);peer=root/'peer';peer.mkdir()
        outline=self.adapter.outline
        (peer/'synthetic-world.json').write_text(json.dumps({'vertices':[a for a,_ in outline['segments']],
            'start':[-.1,-.6,.1],'output_delay_s':delay,'large_observation':large}))
        controller=PhysicalController(root,command=lambda _r,_m:[sys.executable,'-B',
            str(ROOT/'tests/fixtures/idle_reference_robot_process.py'),str(peer)])
        self.addCleanup(controller.close)
        factory=RemoteObservedFactory(controller,root,'reference_room');self.addCleanup(factory.close)
        factory.reference_loader=lambda key:deepcopy(self.prior) if key==self.prior['map_id'] else None
        factory.room_revision_loader=lambda:self.report['goal']['room_revision']
        # Explicit fake review for a local synthetic command; never production SSH.
        with patch('twinpulse_app.remote_observed_adapter.ObservedReleaseRegistration',return_value=lambda scope:{}):
            if delay:
                with self.assertRaisesRegex(ValueError,'TRANSPORT_CHANGED|QUERY_TIMEOUT|WORKER_ENDED'):
                    factory.preview_current('browser',reference_key=self.prior['map_id'])
                self.assertIsNone(factory.idle_job)
                self.assertIsNotNone(controller.snapshot('browser').get('localization_error'))
            else:
                try:first=factory.preview_current('browser',reference_key=self.prior['map_id'])
                except Exception as exc:
                    self.fail(str(exc)+'; state='+str(controller.snapshot('browser'))+'; peer='+
                        ((peer/'idle-report.json').read_text() if (peer/'idle-report.json').exists() else 'not saved')+
                        '; events='+str([(e['kind'],e['data']) for e in controller.journal if e['kind'] in
                            {'localization_query_sent','localization_observation_received','transport_error'}]))
                self.assertEqual(first['evidence']['state'],'TRACKING_CANDIDATE')
                self.assertFalse(first['evidence']['motion_authorized']);self.assertTrue(first['evidence']['cells'])
                self.assertLess(factory.clock()-first['evidence']['sample_s'],.2)
                time.sleep(.02)
                second=factory.preview_current('browser',reference_key=self.prior['map_id'])
                self.assertGreater(second['evidence']['sample_s'],first['evidence']['sample_s'])
                self.assertEqual(first['context'],second['context'])
                with self.assertRaisesRegex(ValueError,'OWNER_CHANGED'):
                    factory.preview_current('other',reference_key=self.prior['map_id'])
                received=json.loads((peer/'reference-received.json').read_text())
                self.assertEqual(received,self.prior)
                self.assertGreater(len(received['map']['tracking_endpoints']),512)
        factory.close()
        self.assertFalse(controller.snapshot('browser')['busy'])
        self.assertIsNone(controller.localization_observation)
        report=json.loads((peer/'idle-report.json').read_text())
        from twinpulse_app.session_history import review_session
        history=review_session(root,controller.job)
        self.assertEqual(history['mode'],'localize');self.assertFalse(history['motion_authorized'])
        journal=[json.loads(line) for line in (root/'artifacts/manual-control'/controller.job/'session.jsonl').read_text().splitlines()]
        saved=[row['data'] for row in journal if row['kind']=='localization_observation_received']
        if not delay:self.assertTrue(saved)
        for item in saved:
            raw=(root/'artifacts/manual-control'/controller.job/('localization-'+item['query_id']+'.json')).read_bytes()
            self.assertEqual(descriptor(raw),item['payload'])
        if large:
            self.assertTrue(any(row['kind']=='localization_ack_sent' for row in journal))
        if not delay:
            self.assertTrue(history['localization_observations'])
            self.assertTrue(all(item['packet_storage']=='HASH_VERIFIED_HISTORICAL' for item in history['localization_observations']))
            retained=root/'artifacts/manual-control'/controller.job/('localization-'+saved[0]['query_id']+'.json')
            original=retained.read_bytes();retained.write_bytes(original+b' ')
            try:
                with self.assertRaisesRegex(Exception,'Saved session'):
                    review_session(root,controller.job)
            finally:retained.write_bytes(original)
        self.assertFalse(any(e.get('linear_m_s',0) or e.get('angular_rad_s',0) for e in report['synthetic_published']))
        self.assertEqual(self.capture.path.read_bytes(),self.capture.original)
        return report

    def test_actual_pc_factory_controller_native_loop_two_queries_close_no_movement(self):
        report=self.execute();self.assertEqual(report['status'],'MISSION_CANCELLED',report)
        self.assertTrue(report['cleanup_confirmed']);self.assertTrue(report['sensor_cleanup_confirmed'])

    def test_delayed_pipe_rejects_old_current_evidence_and_saves_cause(self):
        report=self.execute(.21)
        self.assertNotEqual(report['status'],'MISSION_ARRIVED')
        self.assertTrue(report['cleanup_confirmed'])
        self.assertTrue(report['sensor_cleanup_confirmed'])

    def test_large_observation_uses_ack_chunks_without_grid_truncation(self):
        self.assertEqual(self.execute(large=True)['status'],'MISSION_CANCELLED')

    def test_live_review_absence_never_opens_transport(self):
        with TemporaryDirectory() as temp:
            controller=PhysicalController(temp,command=lambda *_:(_ for _ in ()).throw(AssertionError('STARTED')))
            self.addCleanup(controller.close)
            factory=RemoteObservedFactory(controller,Path(temp),'reference_room')
            factory.reference_loader=lambda _:deepcopy(self.prior)
            factory.room_revision_loader=lambda:self.report['goal']['room_revision']
            with self.assertRaisesRegex(ValueError,'NOT_REGISTERED'):
                factory.preview_current('browser',reference_key=self.prior['map_id'])
            self.assertIsNone(controller.thread)


class IdleLoopSafetyTests(unittest.TestCase):
    def exercise(self,fault):
        # Virtual time and an explicitly device-free link; no hardware admission.
        from tests.fixtures.manual_robot_process import mission_fixture
        from mission_runtime import run_idle_localization
        from types import SimpleNamespace
        t=[10.];queue=deque();output=[];closed=[];queries=[0]
        link=SimpleNamespace(enabled=False,fresh=lambda:None)
        def spin(dt):
            t[0]+=.005
            if fault=='backwards':t[0]-=.01
            if fault=='expired':t[0]+=45.
        link.spin=spin
        def preview():
            queries[0]+=1
            if fault=='post_enabled':link.enabled=True
            if fault=='stale':t[0]+=.21
            return {'sample_s':10.,'cells':[]}
        factory=SimpleNamespace(preview_current=preview,idle_evidence=SimpleNamespace(close=lambda:closed.append(True)))
        def emit(value):
            output.append(value)
            if value['state']=='READY' and len(output)==1:
                packet={'sequence':1,'action':'watch','challenge':value['challenge'],'age_ms':0.}
                if fault=='direction':packet['action']='forward'
                if fault!='no_watch':queue.append(packet)
                if fault not in {'deadline','expired','backwards','direction'}:
                    queue.append({'action':'localization_query','query_id':'a'*32})
                    if fault=='duplicate':queue.append({'action':'localization_query','query_id':'a'*32})
                    elif fault=='close':queue.append({'sequence':2,'action':'close','challenge':None,'age_ms':0.})
        incoming=SimpleNamespace(receive=lambda:queue.popleft() if queue else None)
        request={'adaptive_scope':{'phase':'IDLE_LOCALIZATION_ONLY'},'expires_s':100.}
        try:
            return run_idle_localization(link,incoming,emit,request,factory,clock=lambda:t[0])
        finally:
            self.assertEqual(closed,[True])
            self.assertFalse(any(row.get('state')=='LOCALIZATION_OBSERVATION' for row in output) if fault in {'no_watch','stale','post_enabled'} else False)

    def test_watchdog_scope_and_disabled_checks_never_authorize_directions(self):
        for fault,code in [('no_watch','INPUT_REQUIRED'),('deadline','INPUT_DEADLINE_EXPIRED'),
                           ('expired','EXPIRED'),('backwards','CLOCK_FAULT'),('direction','DIRECTION_REJECTED'),
                           ('post_enabled','WHEELS_NOT_DISABLED'),('stale','CURRENT_EVIDENCE_STALE'),
                           ('duplicate','QUERY_INVALID')]:
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,code):self.exercise(fault)

    def test_explicit_close_invalidates_sampler_without_execution(self):
        result=self.exercise('close')
        self.assertEqual(result['status'],'MISSION_CANCELLED');self.assertIsNone(result['reason'])
