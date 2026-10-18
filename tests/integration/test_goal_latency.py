# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline latency contracts: hash bytes, busy rejection and secret-free profiling."""
from collections import UserDict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import time
import threading
from types import SimpleNamespace
from typing import Mapping
import unittest
from unittest.mock import patch
from twinpulse_core.revisions import canonical_sha256
from twinpulse_app.chat_inspection import ChatInspection
from twinpulse_app.physical_controller import PhysicalController
from scripts.verify_goal_separated_journey import profile_query_receiver


def legacy_sha(value):
    # Frozen algorithm before the exact-builtin optimization; hash oracle.
    def normalize(item):
        if isinstance(item,Mapping):
            if not all(isinstance(key,str) for key in item):raise ValueError('keys')
            return {key:normalize(item[key]) for key in sorted(item)}
        if isinstance(item,(list,tuple)):return [normalize(part) for part in item]
        if isinstance(item,float):
            if not math.isfinite(item):raise ValueError('finite')
            return 0.0 if item==0 else item
        if isinstance(item,(str,int,bool)) or item is None:return item
        raise ValueError('unsupported')
    return hashlib.sha256(json.dumps(normalize(value),ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


class CanonicalParityTests(unittest.TestCase):
    def test_json_grid_and_custom_mapping_subclass_hashes_stay_byte_identical(self):
        class Array(list):pass
        class Object(dict):pass
        corpus=[None,False,True,0,-1,10**80,0.,-0.,.03,'한글 🛑',
            {'z':Array([UserDict({'x':-0.}),(True,None)]),'a':Object({'b':.2})},
            {'cells':[[i,j,'free',i/100.,'a'*64] for i in range(100) for j in range(10)]}]
        rng=random.Random(304)
        for _ in range(120):
            corpus.append({'z':[rng.choice([None,True,False]),rng.random(),rng.randrange(-1000,1000)],
                'a':{'é':[rng.random(),-0.,'x']}})
        for value in corpus:
            before=deepcopy(value)
            self.assertEqual(canonical_sha256(value),legacy_sha(value))
            self.assertEqual(value,before)

    def test_nonfinite_nonstring_keys_and_unsupported_values_still_rejected(self):
        for value in (float('nan'),float('inf'),float('-inf'),{'bad':[float('nan')]},
                      {1:'key'},UserDict({1:'key'}),{1,2},object()):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):canonical_sha256(value)
                with self.assertRaises(ValueError):legacy_sha(value)


class BusyInspectionTests(unittest.TestCase):
    def test_other_active_mission_disables_inspection_without_room_io(self):
        mission=SimpleNamespace(worker=SimpleNamespace(is_alive=lambda:True))
        inspection=ChatInspection(mission,None,None,None)
        result=inspection.readiness('owner')
        self.assertEqual(result['code'],'MISSION_BUSY')
        self.assertFalse(result['ready']);self.assertIsNone(result['binding'])
        self.assertFalse(result['motion_authorized']);self.assertFalse(result['demo_ready'])

    def test_idle_does_not_reuse_busy_or_ready_cache(self):
        mission=SimpleNamespace(worker=SimpleNamespace(is_alive=lambda:False),
            automatic=SimpleNamespace(root=None,photo_store=None))
        inspection=ChatInspection(mission,None,None,None)
        self.assertEqual(inspection.readiness('owner')['code'],'INSPECTION_STORAGE_UNAVAILABLE')


class LateLocalizationTests(unittest.TestCase):
    def controller(self):
        controller=PhysicalController(Path(__file__).resolve().parents[2],clock=lambda:10.)
        controller.mode='localize';controller.job='job';controller.stop_requested=True
        controller.localization_query={'id':'c'*32,'started_s':9.}
        controller.localization_observation=None;controller.localization_received=None
        controller.localization_records=[];controller.localization_bytes=0
        controller.mission_scope={};controller.mission_context={}
        controller._record=lambda *a,**k:None
        return controller

    def test_late_after_stop_is_raw_only_and_does_not_abort_cleanup_reader(self):
        from twinpulse_core.reference_transport import observation_packet,checked_observation
        controller=self.controller();evidence={'sample_s':9.,'physical_demo_ready':False}
        value=observation_packet('c'*32,evidence,9.1)
        with patch('twinpulse_core.reference_transport.checked_observation',
                   side_effect=AssertionError('Stopped packet must not become current')):
            controller._receive_localization(value,'robot')
        self.assertTrue(controller.stop_requested)
        self.assertIsNone(controller.localization_observation)
        self.assertIsNone(controller.localization_received)
        self.assertEqual(len(controller.localization_records),1)
        query,raw=controller.localization_records[0]
        self.assertEqual(query,'c'*32)
        self.assertEqual(checked_observation(json.loads(raw),query),evidence)

    def test_foreign_late_query_cannot_enter_owned_raw_or_pose(self):
        from twinpulse_core.reference_transport import observation_packet
        controller=self.controller()
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_LOCALIZATION_OBSERVATION'):
            controller._receive_localization(observation_packet('d'*32,{'sample_s':9.},9.1),'robot')
        self.assertEqual(controller.localization_records,[])
        self.assertIsNone(controller.localization_observation)


class DiagnosticArchiveTests(unittest.TestCase):
    def test_native_publication_shape_and_limits_not_event_dictionary_guess(self):
        from scripts.verify_goal_separated_journey import synthetic_output_count
        self.assertEqual(synthetic_output_count([]),0)
        self.assertEqual(synthetic_output_count([[0.,0.,.05],[.03,0.,.078],[0.,-.2,.01]]),2)
        for value in ({},[{'linear_m_s':.03}],[[True,0.,.01]],[[.08,0.,.01]],
                      [[0.,.21,.01]],[[0.,0.,-.001]],[[0.,0.,float('nan')]],[[0.,0.]]):
            with self.assertRaises(ValueError):synthetic_output_count(value)

    def test_known_diagnostics_reopen_but_extra_authority_wrong_types_and_unknown_shapes_reject(self):
        from twinpulse_app.session_history import valid_pc
        from twinpulse_core.reference_transport import descriptor
        base={'query_id':'c'*32,'reason':'GOAL_PREVIEW_CURRENT_EVIDENCE_STALE','round_trip_upper_s':.1}
        cases=[('adaptive_visual',{'revision':'d'*64,'validation_s':.02}),
            ('goal_watch_cycle',{'guard_s':.01,'controller_lock_wait_s':.001,'sender_s':.001}),
            ('goal_watch_cycle',{'guard_s':.01,'controller_lock_wait_s':.001,'sender_s':.001,
                                 'receipt_check_s':.003,'source_guard_s':.007}),
            ('goal_handoff_admission_failed',{'phase':'FRESH_QUERY','error_type':'ValueError',
                'reason':'IDLE_LOCALIZATION_QUERY_TIMEOUT','elapsed_s':.3,'evidence_age_upper_s':None}),
            ('localization_late_after_stop',{'query_id':'c'*32,'payload':descriptor(b'{}')}),
            ('localization_partial_after_stop',{'query_id':'c'*32,'state':'LOCALIZATION_CHUNK'}),
            ('localization_return_rejected',{**base,'evidence_age_upper_s':.22,'elapsed_since_receipt_s':None}),
            ('localization_validation_rejected',{**base,'evidence_age_upper_s':.22,'decode_elapsed_s':.01,
                'binding_elapsed_s':.001,'commit_wait_s':.15}),
            ('localization_validation_rejected',{**base,'robot_processing_s':.03,'decode_elapsed_s':.01,
                'transport_time_valid':False,'context_valid':True,'reference_valid':True,'authority_absent':True})]
        for kind,data in cases:
            with self.subTest(kind=kind):
                row={'schema':'control-session-1.0','job_id':'job','event_index':1,'clock_domain':'pc_monotonic',
                     't':10.,'kind':kind,'real_transport':False,'data':data}
                scope={'phase':'IDLE_LOCALIZATION_ONLY'}
                self.assertTrue(valid_pc(row,'job',adaptive=True,scope=scope))
                self.assertFalse(valid_pc(row,'job',adaptive=False,scope=scope))
                self.assertFalse(valid_pc({**row,'data':{**data,'motion_authorized':True}},'job',adaptive=True,scope=scope))
                numeric=next((key for key,value in data.items() if type(value) in (int,float)),None)
                if numeric:
                    for value in (True,float('nan'),float('inf'),1e10):
                        self.assertFalse(valid_pc({**row,'data':{**data,numeric:value}},'job',adaptive=True,scope=scope))


class QueryProfileTests(unittest.TestCase):
    def test_result_exception_and_secret_free_frame_metadata_preserved(self):
        for failing in (False,True):
            with self.subTest(failing=failing),TemporaryDirectory() as temp:
                secret='TEST_PRIVATE_LOCAL_VALUE_305'
                def original(value,session):
                    private_local=secret
                    time.sleep(.012)
                    if failing:raise ValueError(private_local)
                    return {'same':value}
                controller=SimpleNamespace(_receive_localization=original)
                profile_query_receiver(controller,Path(temp))
                if failing:
                    with self.assertRaisesRegex(ValueError,secret):controller._receive_localization(7,'session')
                else:self.assertEqual(controller._receive_localization(7,'session'),{'same':7})
                raw=(Path(temp)/'query-profile-1.json').read_text()
                self.assertNotIn(secret,raw);self.assertNotIn('private_local',raw)
                result=json.loads(raw)
                self.assertTrue(result['diagnostic_only']);self.assertTrue(result['sampler_exited'])
                self.assertEqual(result['failure_type'],'ValueError' if failing else None)


class HandoffInputTests(unittest.TestCase):
    def controller(self,temp):
        controller=PhysicalController(Path(temp),command=lambda *_:[])
        controller.owner='owner';controller.job='a'*32;controller.mode='localize'
        controller.thread=SimpleNamespace(is_alive=lambda:True,join=lambda **_:None)
        controller.state={'state':'READY','localization_input_sequence':1}
        controller.mission_scope={'scope':'test'}
        controller.localization_observation={'context':{'source':'current'}}
        controller.mission_admission=lambda _:{}
        controller._record=lambda *args,**kwargs:None
        controller.snapshot=lambda _:dict(controller.state)
        controller.challenge='c'*24;controller.challenge_at=controller.clock()
        (controller.root/'artifacts/manual-control'/controller.job).mkdir(parents=True)
        self.addCleanup(controller.close)
        return controller

    def plan(self):
        return {'schema':'current-goal-preview-2.0','plan_id':'b'*64,
                'binding':{'context':{'source':'current'}}}

    def handoff_patches(self):
        return (patch('twinpulse_core.reference_transport.goal_handoff',
                      side_effect=lambda scope,job,preview:{'scope':scope,'preview':preview}),
                patch('twinpulse_core.current_goal_preview.review_source_matches',return_value=True))

    def packet(self,controller):
        return json.loads(controller.writes.get_nowait())

    def test_pending_exact_handoff_forwards_watch_without_new_lease_or_directions(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp)
            first,second=self.handoff_patches()
            with first,second:c.handoff_goal('owner',c.job,self.plan())
            self.assertEqual(self.packet(c)['action'],'goal_handoff_begin')
            before=c.challenge
            c.input('owner',c.job,1,'watch',c.wall()+200)
            sent=self.packet(c)
            self.assertEqual(sent['action'],'watch');self.assertEqual(sent['challenge'],before)
            self.assertGreaterEqual(sent['age_ms'],49.)
            self.assertEqual(c.state['state'],'HANDOFF_PENDING')
            with self.assertRaisesRegex(Exception,'Mission selects directions'):
                c.input('owner',c.job,2,'forward',c.wall()+200)
            self.assertTrue(c.stop_requested)

    def test_unbound_pending_state_does_not_forward_watch(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp);c.state={'state':'HANDOFF_PENDING'}
            c.input('owner',c.job,1,'watch',c.wall()+200)
            self.assertTrue(c.writes.empty());self.assertIsNone(c.pending_input)

    def test_force_stop_during_pending_transfer_sends_explicit_stop_not_only_eof(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp);first,second=self.handoff_patches()
            with first,second:c.handoff_goal('owner',c.job,self.plan())
            self.assertEqual(self.packet(c)['action'],'goal_handoff_begin')
            c.input('owner',c.job,1,'force_stop',0)
            self.assertEqual(self.packet(c)['action'],'force_stop')
            self.assertEqual(c.state['state'],'STOPPING');self.assertTrue(c.stop_requested)

    def test_slow_durable_save_keeps_watch_and_force_stop_responsive_no_late_begin(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp);entered=threading.Event();release=threading.Event();failures=[]
            def slow_sync(_):
                entered.set()
                if not release.wait(2.):raise TimeoutError('TEST_SYNC_NOT_RELEASED')
            def send():
                try:c.handoff_goal('owner',c.job,self.plan())
                except Exception as exc:failures.append(str(exc))
            first,second=self.handoff_patches()
            with first,second,patch('twinpulse_app.physical_controller.os.fsync',side_effect=slow_sync):
                thread=threading.Thread(target=send);thread.start()
                try:
                    self.assertTrue(entered.wait(1.))
                    self.assertTrue(c.lock.acquire(timeout=.2))
                    c.lock.release()
                    with self.assertRaisesRegex(ValueError,'NOT_OWNED_IDLE'):
                        c.handoff_goal('owner',c.job,self.plan())
                    with self.assertRaisesRegex(Exception,'wheel-disabled'):
                        c.query_localization('owner',c.job,'d'*32)
                    c.input('owner',c.job,1,'watch',c.wall()+200)
                    self.assertEqual(self.packet(c)['action'],'watch')
                    c.input('owner',c.job,2,'force_stop',0)
                    self.assertEqual(self.packet(c)['action'],'force_stop')
                finally:release.set();thread.join(2.)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures,['GOAL_HANDOFF_SOURCE_CHANGED_OR_STOPPED'])
            self.assertIsNone(c.goal_handoff_value);self.assertIsNone(c.goal_handoff_reservation)
            self.assertTrue(c.stop_requested)
            self.assertTrue((c.root/'artifacts/manual-control'/c.job/'goal-handoff.json').is_file())
            self.assertTrue(c.writes.empty())

    def test_disk_failure_retains_original_cause_and_never_sends_handoff(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp);first,second=self.handoff_patches()
            with first,second,patch('twinpulse_app.physical_controller.os.fsync',side_effect=OSError('TEST_DISK_FAILED')):
                with self.assertRaisesRegex(OSError,'TEST_DISK_FAILED'):
                    c.handoff_goal('owner',c.job,self.plan())
            self.assertIsNone(c.goal_handoff_value);self.assertIsNone(c.goal_handoff_reservation)
            self.assertTrue(c.writes.empty());self.assertEqual(c.state['state'],'READY')

    def test_source_change_during_save_cannot_be_transferred(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp);first,second=self.handoff_patches()
            def changed(_):c.localization_observation={'context':{'source':'changed'}}
            with first,second,patch('twinpulse_app.physical_controller.os.fsync',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_OR_STOPPED'):
                    c.handoff_goal('owner',c.job,self.plan())
            self.assertIsNone(c.goal_handoff_value);self.assertTrue(c.writes.empty())

    def test_slow_visual_validation_does_not_block_input_or_restore_after_stop(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp);c.mission_scope={'schema':'observed-mission-scope-7.0'}
            entered=threading.Event();release=threading.Event();failures=[]
            def validate(*args,**kwargs):
                entered.set()
                if not release.wait(2.):raise TimeoutError('TEST_VALIDATION_NOT_RELEASED')
                return {'revision':'e'*64}
            def receive():
                try:c._receive_adaptive_visual({'raw':'test'})
                except Exception as exc:failures.append(exc)
            with patch('twinpulse_app.remote_observed_adapter.checked_remote_visual',side_effect=validate):
                thread=threading.Thread(target=receive);thread.start()
                try:
                    self.assertTrue(entered.wait(1.));self.assertTrue(c.lock.acquire(timeout=.2));c.lock.release()
                    c.input('owner',c.job,1,'watch',c.wall()+200)
                    self.assertEqual(self.packet(c)['action'],'watch')
                    c.input('owner',c.job,2,'force_stop',0)
                finally:release.set();thread.join(2.)
            self.assertFalse(thread.is_alive());self.assertEqual(failures,[])
            self.assertIsNone(c.adaptive_visual);self.assertTrue(c.stop_requested)

    def test_visual_source_replacement_rejected_at_commit(self):
        with TemporaryDirectory() as temp:
            c=self.controller(temp);c.mission_scope={'schema':'observed-mission-scope-7.0'}
            def validate(*args,**kwargs):
                c.mission_scope=dict(c.mission_scope)
                return {'revision':'e'*64}
            with patch('twinpulse_app.remote_observed_adapter.checked_remote_visual',side_effect=validate):
                with self.assertRaisesRegex(ValueError,'VISUAL_SOURCE_CHANGED'):
                    c._receive_adaptive_visual({'raw':'test'})
            self.assertIsNone(c.adaptive_visual)


if __name__=='__main__':unittest.main()
