# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free exact-plan transfer, native guard and current-owner regression.

The positive estimator is an explicit stable synthetic double. No live target,
real localization tolerance, Isaac renderer or physical acceptance is asserted.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from threading import Thread
import json
import sys
import time
import unittest
from twinpulse_core.reference_transport import goal_handoff,checked_goal_handoff
from twinpulse_core.adaptive_mission_contract import adaptive_bootstrap
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.current_goal_preview import goal_preview
from twinpulse_app.physical_controller import PhysicalController
from twinpulse_app.remote_observed_adapter import RemoteObservedFactory
from tests.integration.test_current_goal_preview import evidence
from tests.integration.test_scene_changes import room_source
from tests.integration.test_reference_transport import RemoteIdleTests,ROOT
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from tests.integration.test_chat_goal_navigation import ChatGoalTests
from collections import deque
from types import SimpleNamespace
from twinpulse_core.reference_transport import ReferenceSender


class GoalHandoffContractTests(unittest.TestCase):
    def test_exact_scope_context_digest_and_fresh_source(self):
        e=evidence();context={k:e[k] for k in ('project_id','source_revision','epoch')}
        plan=goal_preview(room_source().site.scene,'Go x=.3 y=-1.8',e,context,1.)['plan']
        scope={'schema':'observed-mission-scope-6.0','phase':'IDLE_LOCALIZATION_ONLY',
            'project_id':e['project_id'],'goal':{**plan['goal_contract'],'xy':[0.,0.]},
            'reference':{'kind':'accepted-survey-reference-1.0','revision':'a'*64,'payload':{'sha256':'b'*64,'bytes':20000}},
            'alignment':{'status':'ALIGNMENT_CANDIDATE','room_from_map':e['room_from_map'],'report_revision':e['alignment_revision']}}
        value=goal_handoff(scope,'a'*32,plan)
        self.assertEqual(checked_goal_handoff(value,scope,'a'*32,e,context,1.),value)
        self.assertEqual(value['preview']['route'],plan['route'])
        for fault in ('id','route','pose','source','stale','alignment'):
            bad=deepcopy(value);current=deepcopy(e);identity='a'*32;now=1.
            if fault=='id':identity='b'*32
            if fault=='route':bad['preview']['route'][0][0]+=.01
            if fault=='pose':current['pose_map'][0]+=.001
            if fault=='source':current['source_revision']='f'*64
            if fault=='stale':now=2.
            if fault=='alignment':
                bad['preview']['binding']['alignment_revision']='e'*64
                bad['preview']['plan_id']=canonical_sha256({k:v for k,v in bad['preview'].items() if k!='plan_id'})
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                checked_goal_handoff(bad,scope,identity,current,context,now)
        with self.assertRaisesRegex(ValueError,'REQUIRES_IDLE'):
            adaptive_bootstrap({'state':'MISSION_CONTEXT','boot_id':'b','release_id':'a'*64,'calibration_sha256':'b'*64,
                'issued_s':1.,'nonce':'a'*24},'a'*32,value['scope'])

    def test_native_transfer_keeps_input_gate_and_original_budget_and_stop(self):
        from mission_runtime import run_idle_localization
        for fault in ('none','stop','deadline','expired','nonce'):
            with self.subTest(fault=fault):
                e=evidence();e['sample_s']=10.;context={k:e[k] for k in ('project_id','source_revision','epoch')}
                plan=goal_preview(room_source().site.scene,'Go x=.3 y=-1.8',e,context,10.)['plan']
                scope={'schema':'observed-mission-scope-6.0','phase':'IDLE_LOCALIZATION_ONLY',
                    'project_id':e['project_id'],'goal':{**plan['goal_contract'],'xy':[0.,0.]},
                    'reference':{'kind':'accepted-survey-reference-1.0','revision':'a'*64,
                        'payload':{'sha256':'b'*64,'bytes':20000}},
                    'alignment':{'status':'ALIGNMENT_CANDIDATE','room_from_map':e['room_from_map'],
                        'report_revision':e['alignment_revision']}}
                value=goal_handoff(scope,'a'*32,plan);sender=ReferenceSender(value);packets=deque();closed=[];t=[10.]
                request={'adaptive_scope':scope,'mission_id':'a'*32,'expires_s':100.}
                link=SimpleNamespace(enabled=False,fresh=lambda:None,spin=lambda _:t.__setitem__(0,t[0]+.005))
                def accepted(payload):
                    checked=checked_goal_handoff(payload,scope,'a'*32,e,context,t[0])
                    request['adaptive_scope']=checked['scope'];return checked
                factory=SimpleNamespace(accept_goal_handoff=accepted,
                    idle_evidence=SimpleNamespace(close=lambda:closed.append(True)))
                def emit(row):
                    if row['state']=='READY':
                        packets.append({'sequence':1,'action':'watch','challenge':row['challenge'],'age_ms':0.})
                        packets.append({'action':'goal_handoff_begin','payload':sender.descriptor,'nonce':'c'*24})
                    elif row['state']=='GOAL_HANDOFF_NEXT':
                        if fault=='stop':
                            packets.append({'sequence':2,'action':'force_stop','challenge':None,'age_ms':0.});return
                        if fault=='deadline':t[0]+=.251
                        if fault=='expired':t[0]+=45.
                        chunk=sender.chunk(row['nonce'],row['index'])
                        if fault=='nonce':chunk['nonce']='d'*24
                        packets.append(chunk)
                incoming=SimpleNamespace(receive=lambda:packets.popleft() if packets else None)
                def running(*args,**kwargs):
                    self.assertEqual(kwargs['input_gate'].sequence,1)
                    self.assertEqual(request['expires_s'],55.)
                    self.assertFalse(link.enabled)
                    return {'status':'TEST_ONLY_TRANSITION_NOT_MOVEMENT'}
                with patch('mission_runtime.run_mission',side_effect=running) as run:
                    if fault in {'deadline','expired','nonce'}:
                        with self.assertRaises(ValueError):run_idle_localization(link,incoming,emit,request,factory,
                            clock=lambda:t[0],record=lambda *_,**__:None,consume=lambda:None)
                        run.assert_not_called()
                    else:
                        result=run_idle_localization(link,incoming,emit,request,factory,
                            clock=lambda:t[0],record=lambda *_,**__:None,consume=lambda:None)
                        self.assertEqual(result['status'],'MISSION_CANCELLED' if fault=='stop' else 'TEST_ONLY_TRANSITION_NOT_MOVEMENT')
                        self.assertEqual(run.call_count,0 if fault=='stop' else 1)
                self.assertEqual(closed,[True]);self.assertFalse(link.enabled)


class RemoteGoalHandoffTests(unittest.TestCase):
    setUpClass=classmethod(RemoteIdleTests.setUpClass.__func__)
    tearDownClass=classmethod(RemoteIdleTests.tearDownClass.__func__)

    def execute(self,*,stable,force=False,post_enable=False,receipt_lost=False,revalidate=False,park=False,slow_record=False):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name);peer=root/'peer';peer.mkdir()
        outline=self.adapter.outline
        (peer/'synthetic-world.json').write_text(json.dumps({'vertices':[a for a,_ in outline['segments']],
            'start':[-.1,-.6,.1],'stable_review_test_only':stable,'post_enable_pose_change_test_only':post_enable,
            'unique_sessions':park,'post_enable_delta_test_only':.011 if revalidate else .001}))
        controller=PhysicalController(root,command=lambda _r,_m:[sys.executable,'-B',
            str(ROOT/'tests/fixtures/idle_reference_robot_process.py'),str(peer)])
        self.addCleanup(controller.close)
        factory=RemoteObservedFactory(controller,root,'reference_room');self.addCleanup(factory.close)
        factory.reference_loader=lambda _:deepcopy(self.prior)
        factory.room_revision_loader=lambda:self.report['goal']['room_revision']
        events=[];visuals=[];result=[]
        with patch('twinpulse_app.remote_observed_adapter.ObservedReleaseRegistration',return_value=lambda scope:{}):
            current=factory.preview_current('browser',reference_key=self.prior['map_id'])
            from twinpulse_core.room_localization import compose
            e=current['evidence'];start=compose(e['room_from_map'],e['pose_map'])
            target=[start[0]+.15,start[1]]
            # Source scene is explicit fixture geometry, not a measured photo.
            plan=goal_preview(room_source().site.scene,f'Go x={target[0]} y={target[1]}',e,current['context'],factory.clock(),
                revalidate_route=revalidate)['plan']
            if park:
                previous_job=controller.job
                factory.park_review('browser',self.prior['map_id'],plan)
                self.assertFalse(controller.snapshot('browser')['busy'])
                self.assertIsNone(factory.idle_job)
                self.assertTrue(factory.owns_review('browser',self.prior['map_id'],plan))
                before=len(controller.journal)
                # Review wall time exceeds45s in the parked PC clock; there is
                # no idle worker, active input gate or retained current pose.
                real_clock=controller.clock
                controller.clock=lambda:real_clock()+90.
                self.assertTrue(factory.owns_review('browser',self.prior['map_id'],plan))
                self.assertEqual(len(controller.journal),before)
                controller.clock=real_clock
                resumed=factory.resume_review('browser',self.prior['map_id'],plan)
                self.assertNotEqual(controller.job,previous_job)
                self.assertNotEqual(resumed['context']['session_id'],current['context']['session_id'])
                with self.assertRaisesRegex(ValueError,'RESERVATION_CHANGED'):
                    factory.resume_review('browser',self.prior['map_id'],plan)
            old_thread=controller.thread;old_job=controller.job
            adapter=factory.prepare_goal_handoff('browser',self.prior['map_id'],self.prior,
                {'effective_revision':self.report['goal']['room_revision']},plan)
            adapter.bind_session('b'*32);adapter.admit(plan['goal_contract'])
            with self.assertRaisesRegex(ValueError,'OWNED_IDLE'):
                factory.prepare_goal_handoff('other',self.prior['map_id'],self.prior,
                    {'effective_revision':self.report['goal']['room_revision']},plan)
            def run():
                delayed=[False]
                def record(kind,**data):
                    events.append((kind,data))
                    if slow_record and not delayed[0] and kind=='mission_started':
                        delayed[0]=True;time.sleep(.35)
                try:result.append(adapter.run(record=record,
                    visual=lambda value:visuals.append(value),safety=(lambda:(_ for _ in ()).throw(
                        ValueError('GOAL_DEMONSTRATION_RECEIPT_INVALIDATED'))) if receipt_lost else lambda:None))
                except Exception as exc:result.append(exc)
                finally:adapter.close()
            thread=Thread(target=run);thread.start()
            deadline=time.monotonic()+15.
            while thread.is_alive() and time.monotonic()<deadline:
                if force and controller.mode=='mission':adapter.stop_requested=lambda:'force_stop'
                time.sleep(.01)
            if thread.is_alive():adapter.stop_requested=lambda:'force_stop'
            thread.join(24)
            self.assertFalse(thread.is_alive(),controller.snapshot('browser'))
            self.assertIs(controller.thread,old_thread);self.assertEqual(controller.job,old_job)
        report=json.loads((peer/'idle-report.json').read_text())
        if (stable or revalidate) and not receipt_lost:
            self.assertTrue(controller.goal_handoff_receipt,result)
            if post_enable:
                self.assertIsInstance(result[0],Exception)
                self.assertIn('GOAL_PREVIEW_START_OUTSIDE_REVIEW_ENVELOPE' if revalidate else 'GOAL_PREVIEW_START_MAP_OR_SOURCE_CHANGED',str(result[0]))
                self.assertFalse(any(row[0] or row[1] for row in report['synthetic_published']))
            else:
                self.assertNotIsInstance(result[0],Exception,repr(result[0])+'; '+str(report))
                self.assertEqual(result[0]['status'],'FORCE_STOPPED' if force else 'MISSION_ARRIVED')
                if not force:self.assertTrue(any(row[0] or row[1] for row in report['synthetic_published']),report)
            saved=json.loads((peer/'goal-handoff.json').read_text())
            self.assertEqual(saved['preview'],plan)
            self.assertTrue((peer/('consumed-'+old_job)).is_file())
            from twinpulse_app.session_history import review_session
            history=review_session(root,old_job)
            self.assertTrue(history['goal_handoff']['accepted']);self.assertFalse(history['motion_authorized'])
            raw_path=root/'artifacts/manual-control'/old_job/'goal-handoff.json'
            original=raw_path.read_bytes();raw_path.write_bytes(original+b' ')
            try:
                with self.assertRaisesRegex(Exception,'Saved session'):review_session(root,old_job)
            finally:raw_path.write_bytes(original)
        else:
            self.assertIsInstance(result[0],Exception)
            self.assertIn('RECEIPT_INVALIDATED' if receipt_lost else 'GOAL_PREVIEW_START_MAP_OR_SOURCE_CHANGED',str(result[0]))
            self.assertFalse(any(row[0] or row[1] for row in report['synthetic_published']))
        self.assertTrue(report['cleanup_confirmed']);self.assertTrue(report['sensor_cleanup_confirmed'])
        self.assertEqual(self.capture.path.read_bytes(),self.capture.original)

    def test_same_worker_full_reference_exact_plan_guarded_arrival(self):self.execute(stable=True)
    def test_same_worker_explicit_force_stop_no_reconnect(self):self.execute(stable=True,force=True)
    def test_real_estimator_shape_jitter_rejects_not_tolerance_relaxed(self):self.execute(stable=False)
    def test_pose_changed_after_motor_enable_first_output_stays_zero(self):self.execute(stable=True,post_enable=True)
    def test_lost_sim_receipt_closes_idle_without_any_handoff(self):self.execute(stable=True,receipt_lost=True)
    def test_fresh_route_revalidation_with_existing_matcher_no_frozen_pose(self):self.execute(stable=False,revalidate=True)
    def test_parked_review_reopens_once_new_session_then_same_worker_execution(self):self.execute(stable=False,revalidate=True,park=True)
    def test_revalidated_pose_change_during_enable_first_output_stays_zero(self):self.execute(stable=True,post_enable=True,revalidate=True)
    def test_revalidated_receipt_loss_prevents_handoff(self):self.execute(stable=False,revalidate=True,receipt_lost=True)

    def test_slow_report_recording_does_not_block_scoped_fresh_goal_watches(self):
        self.execute(stable=False,revalidate=True,slow_record=True)


class ChatGoalHandoffTests(ChatGoalTests):
    def parked_navigation(self):
        # Legacy receipt/prior doubles isolate chat lifecycle; these cannot
        # establish actual engine, qualification, reference or physical PASS.
        from unittest.mock import Mock
        nav=self.configure(receipt=True);factory=self.mission.adapter_factory
        factory.supports_route_revalidation=True
        factory.park_review=Mock();factory.discard_review=Mock();factory.close_idle=Mock()
        return nav,factory

    def test_chat_parks_before_review_and_refresh_does_not_query_or_resume(self):
        nav,factory=self.parked_navigation();state=self.goal()
        plan=state['navigation']['review']['plan']
        self.assertEqual(plan['schema'],'current-goal-preview-2.0')
        factory.park_review.assert_called_once_with(nav.owner,'fixture-prior',plan)
        reads=self.reads
        for _ in range(3):self.call()
        self.assertEqual(self.reads,reads)
        self.assertEqual(self.starts,[])
        nav.cancel(nav.owner);factory.discard_review.assert_called_with(nav.owner)
        factory.close_idle.assert_called_with(nav.owner)

    def test_expired_parked_confirmation_discards_without_transport(self):
        nav,factory=self.parked_navigation();state=self.goal();body=self.confirmation(state)
        body['expires_at_ms']=0
        self.call(body);self.assertIsNone(nav.review);self.assertEqual(self.starts,[])
        factory.discard_review.assert_called_with(nav.owner);factory.close_idle.assert_called_with(nav.owner)

    def test_rejected_fresh_pose_closes_worker_and_retains_exact_cause(self):
        nav,factory=self.parked_navigation();state=self.goal();self.current['pose_map'][0]+=.011
        result=self.call(self.confirmation(state))
        self.assertIn('GOAL_PREVIEW_START_OUTSIDE_REVIEW_ENVELOPE',result['messages'][-1]['content'])
        self.assertEqual(self.starts,[]);self.assertIsNone(self.mission.worker)
        factory.close_idle.assert_called_with(nav.owner)

    def test_registered_handoff_used_instead_of_legacy_factory_and_only_owned_idle_exemption(self):
        nav=self.configure(receipt=True)
        factory=self.mission.adapter_factory
        factory.supports_exact_goal_handoff=True
        factory.owns_idle=lambda owner,key:owner==nav.owner and key=='fixture-prior'
        calls=[]
        def handoff(owner,key,prior,effective,review):
            calls.append((owner,key,review['plan_id']));raise ValueError('OFFLINE_HANDOFF_BOUNDARY_TEST')
        factory.prepare_goal_handoff=handoff
        state=self.goal();self.call(self.confirmation(state))
        deadline=time.monotonic()+2.
        while self.mission.worker and self.mission.worker.is_alive() and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(len(calls),1);self.assertEqual(self.starts,[])
        self.assertEqual(self.mission.job['error'],'OFFLINE_HANDOFF_BOUNDARY_TEST')
        self.call();self.assertEqual(len(calls),1)
