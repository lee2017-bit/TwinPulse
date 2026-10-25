# SPDX-License-Identifier: Apache-2.0
"""Supplementary finite-clock tests, not App/physical acceptance."""
from threading import RLock,Thread,Event
from types import SimpleNamespace
import unittest
from pathlib import Path
import sys
import json
import io
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
for package in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.engine_loss_probe import EngineLossProbe
from twinpulse_app.workspace_devices import WorkspaceDevices
from twinpulse_app.physical_fleet_adapter import PhysicalFleetAdapter
from twinpulse_app.command_broker import BrokerError,CommandBroker


class EngineLossProbeTests(unittest.TestCase):
    def setUp(self):self.now=0.;self.probe=EngineLossProbe(lambda:self.now)
    def sample(self,sequence,*,connected=False,physical=False,engine='e'):
        return dict(status_sample_id=sequence,engine_session_id=engine,engine_connected=connected,physical_runtime_active=physical)
    def test_idle_recovers_without_process_exit_or_old_command_resume(self):
        self.assertEqual(self.probe.observe(self.sample(1)),'pending')
        self.now=.562
        self.assertEqual(self.probe.observe(self.sample(2,connected=True)),'healthy')
        self.assertEqual(self.probe.stale_samples,0)
    def test_same_publication_is_not_two_samples_and_frozen_file_is_finite(self):
        for now in (0.,.25,.5,1.,2.99):
            self.now=now;self.assertEqual(self.probe.observe(self.sample(1)),'pending')
        self.assertEqual(self.probe.stale_samples,1)
        self.now=3.;self.assertEqual(self.probe.observe(self.sample(1)),'failed')
    def test_distinct_consecutive_stale_reports_confirm_loss(self):
        self.assertEqual(self.probe.observe(self.sample(1)),'pending')
        self.now=1.;self.assertEqual(self.probe.observe(self.sample(2)),'failed')
    def test_rapid_rewrites_do_not_shorten_confirmation_window(self):
        self.assertEqual(self.probe.observe(self.sample(1)),'pending')
        self.now=.1;self.assertEqual(self.probe.observe(self.sample(2)),'pending')
        self.now=1.;self.assertEqual(self.probe.observe(self.sample(2)),'failed')
    def test_active_unknown_or_invalid_physical_proof_never_gets_grace(self):
        for physical in (True,None,0,'false'):
            with self.subTest(physical=physical):self.assertEqual(self.probe.observe(self.sample(1,physical=physical)),'failed')
        self.assertEqual(self.probe.observe(None),'failed')
    def test_new_physical_activity_during_probe_keeps_immediate_failure(self):
        self.assertEqual(self.probe.observe(self.sample(1)),'pending')
        self.now=.25;self.assertEqual(self.probe.observe(self.sample(2,physical=True)),'failed')
    def test_frozen_healthy_report_does_not_stay_green_forever(self):
        self.assertEqual(self.probe.observe(self.sample(1,connected=True)),'healthy')
        self.now=3.;self.assertEqual(self.probe.observe(self.sample(1,connected=True)),'failed')
    def test_changing_stale_identity_does_not_allow_unbounded_wait(self):
        for i in range(3):
            self.now=float(i);self.assertEqual(self.probe.observe(self.sample(i+1,engine=str(i))),'pending')
        self.now=3.;self.assertEqual(self.probe.observe(self.sample(4,engine='four')),'failed')
    def test_regressed_sample_cannot_refresh_progress(self):
        self.assertEqual(self.probe.observe(self.sample(2,connected=True)),'healthy')
        self.now=3.;self.assertEqual(self.probe.observe(self.sample(1,connected=True)),'failed')
    def test_unknown_old_producer_cannot_qualify_stale_grace(self):
        self.assertEqual(self.probe.observe(dict(engine_session_id='e',engine_connected=False,physical_runtime_active=False)),'failed')
    def test_idle_proof_checks_owned_pool_and_uncertain_cleanup_without_transport(self):
        devices=WorkspaceDevices();self.assertFalse(devices.physical_runtime_active())
        row=SimpleNamespace(owner='o',disconnected=False,cleanup_uncertain=False)
        devices.physical_fleet=SimpleNamespace(lock=RLock(),sessions={'r':row})
        self.assertTrue(devices.physical_runtime_active())
        row.disconnected=True;self.assertFalse(devices.physical_runtime_active())
        row.cleanup_uncertain=True;self.assertTrue(devices.physical_runtime_active())
    def test_contended_lock_is_unknown_not_idle(self):
        devices=WorkspaceDevices();started=Event();release=Event()
        def hold():
            with devices.lock:started.set();release.wait(2.)
        thread=Thread(target=hold);thread.start();started.wait(1.)
        try:self.assertTrue(devices.physical_runtime_active())
        finally:release.set();thread.join(1.)
    def test_current_finished_legacy_uncertainty_is_not_historical_idle(self):
        done=SimpleNamespace(is_alive=lambda:False)
        for state in ('FAILED','CONNECTION_LOST'):
            devices=WorkspaceDevices();devices.controller=SimpleNamespace(lock=RLock(),thread=done,
                owner='current',job={},state={'state':state,'cleanup_confirmed':False})
            self.assertTrue(devices.physical_runtime_active())
            devices.controller.owner=None;devices.controller.job=None
            self.assertFalse(devices.physical_runtime_active())
        devices=WorkspaceDevices();devices.readiness=SimpleNamespace(_lock=RLock(),_thread=done,
            _resume_thread=None,_state={'status':'REMOTE_STATE_UNKNOWN'})
        self.assertTrue(devices.physical_runtime_active())
        devices.readiness._state['status']='LOCAL_RECORD_UNREADABLE'
        self.assertTrue(devices.physical_runtime_active())
        devices.readiness._thread=None
        self.assertFalse(devices.physical_runtime_active())
    def test_connect_waiting_before_stale_rechecks_both_admissions_under_start_lock(self):
        from twinpulse_app.robot_registry_service import RobotRegistryService
        for kind in ('pooled','registry'):
            devices=WorkspaceDevices();waiting=Event();outcomes=[]
            adapter=PhysicalFleetAdapter.__new__(PhysicalFleetAdapter);adapter.devices=devices
            registry=RobotRegistryService.__new__(RobotRegistryService);registry.devices=devices
            def delayed_request():
                waiting.set() # Outer gate was already passed while healthy.
                with devices.lock:
                    try:
                        if kind=='pooled':adapter._admission(None,'operator')
                        else:registry._admission()
                        outcomes.append('TRANSPORT_WOULD_START')
                    except BrokerError as error:outcomes.append(error.code)
            with devices.lock:
                thread=Thread(target=delayed_request);thread.start();self.assertTrue(waiting.wait(1.))
                devices.set_engine_process_probe_blocked(True)
            thread.join(1.);self.assertFalse(thread.is_alive())
            self.assertEqual(outcomes,['engine_observation_stale'])
    def test_unchanged_flag_publication_never_waits_for_connect_local_io_lock(self):
        for blocked in (False,True):
            devices=WorkspaceDevices();devices.set_engine_process_probe_blocked(blocked)
            held=Event();release=Event();published=Event()
            def connect_local_io():
                with devices.lock:held.set();release.wait(2.)
            def publish():
                devices.set_engine_process_probe_blocked(blocked)
                published.set()
            worker=Thread(target=connect_local_io);worker.start();self.assertTrue(held.wait(1.))
            publisher=Thread(target=publish);publisher.start()
            try:self.assertTrue(published.wait(.5),'Unchanged sample publication blocked on Connect')
            finally:release.set();publisher.join(1.);worker.join(1.)
    def test_common_physical_command_gate_blocks_before_any_transport(self):
        adapter=PhysicalFleetAdapter.__new__(PhysicalFleetAdapter)
        adapter.devices=SimpleNamespace(engine_process_probe_blocked=True)
        for action in ('drive','task','prepare','qualify','field_arm','field_test'):
            with self.subTest(action=action),self.assertRaises(BrokerError) as caught:adapter._live_command('r','operator',action,{})
            self.assertEqual(caught.exception.code,'engine_observation_stale')
    def test_stale_engine_expiry_revokes_old_control_generation(self):
        broker=CommandBroker();old=broker.acquire_lease('operator')['control_lease_id']
        broker._expire_engine_operations('engine_disconnected')
        with self.assertRaises(BrokerError):broker.renew_lease('operator',old)
        self.assertNotEqual(broker.acquire_lease('operator')['control_lease_id'],old)
    def test_status_read_retries_only_io_and_retains_actual_sample_and_failure(self):
        from twinpulse_app.process_manager import _read_engine_status
        sample=self.sample(7,connected=True);sample['sampled_at_utc']='original-clock'
        with patch('twinpulse_app.process_manager._read_engine_status_bytes',side_effect=[PermissionError(13,'local sharing'),json.dumps(sample).encode()]) as opened:
            value,info=_read_engine_status(Path('status.json'))
        self.assertEqual(value,sample);self.assertEqual(opened.call_count,2)
        self.assertEqual(info['failures'][0]['type'],'PermissionError')
        self.assertEqual(self.probe.observe(value),'healthy')
    def test_status_read_persistent_failure_is_not_cached_healthy(self):
        from twinpulse_app.process_manager import _read_engine_status
        self.assertEqual(self.probe.observe(self.sample(1,connected=True)),'healthy')
        with patch('twinpulse_app.process_manager._read_engine_status_bytes',side_effect=PermissionError(13,'local sharing')) as opened:
            value,info=_read_engine_status(Path('status.json'))
        self.assertEqual(opened.call_count,3);self.assertIsNone(value)
        self.assertEqual(info['reason'],'status_read_failed');self.assertEqual(self.probe.observe(value),'failed')
    def test_successfully_read_active_stale_or_invalid_marker_is_never_retried_to_healthy(self):
        from twinpulse_app.process_manager import _read_engine_status
        for sample in (self.sample(2,physical=True),{},dict(status_sample_id=0,engine_connected=False)):
            with patch('twinpulse_app.process_manager._read_engine_status_bytes',return_value=json.dumps(sample).encode()) as opened:
                value,info=_read_engine_status(Path('status.json'))
            self.assertEqual(value,sample);self.assertEqual(opened.call_count,1)
            self.assertEqual(self.probe.observe(value),'failed')
    def test_successfully_read_regressed_marker_keeps_original_rejection(self):
        from twinpulse_app.process_manager import _read_engine_status
        self.assertEqual(self.probe.observe(self.sample(5,connected=True)),'healthy')
        with patch('twinpulse_app.process_manager._read_engine_status_bytes',return_value=json.dumps(self.sample(4,connected=True)).encode()) as opened:
            value,info=_read_engine_status(Path('status.json'))
        self.assertEqual(opened.call_count,1);self.assertEqual(self.probe.observe(value),'failed')
    def test_healthy_rewrite_of_same_marker_cannot_revive_stale_state(self):
        self.assertEqual(self.probe.observe(self.sample(1)),'pending')
        self.now=.25;self.assertEqual(self.probe.observe(self.sample(1,connected=True)),'failed')
    def test_actual_monitor_recovers_idle_but_keeps_owned_children_and_original_commands_expired(self):
        from tests.integration.test_r6_process_manager import R6ProcessManagerTests,FakeProcess
        fixture=R6ProcessManagerTests();fixture.setUp()
        try:
            manager=fixture.manager(clock=lambda:self.now);manager.launch_dir.mkdir(parents=True)
            backend,engine=FakeProcess(1701),FakeProcess(1702);manager._owned={'backend':backend,'engine':engine}
            manager.engine_status_file.write_text(json.dumps(self.sample(1)),encoding='utf-8')
            def advance(_delay):
                self.now+=.25
                if self.now==.75:manager.engine_status_file.write_text(json.dumps(self.sample(2,connected=True)),encoding='utf-8')
                if self.now>=1.:manager.launcher_shutdown_file.write_text(json.dumps({'schema_version':'1.0','action':'shutdown'}),encoding='utf-8')
            manager._sleep=advance
            self.assertEqual(manager.monitor(poll_s=.25),0)
            self.assertIsNone(manager._terminal_error)
            self.assertFalse(engine.terminated);self.assertFalse(backend.terminated)
            self.assertEqual(json.loads(manager.supervisor_status_file.read_text(encoding='utf-8'))['phase'],'engine_recovered')
        finally:fixture.tearDown()


if __name__=='__main__':unittest.main()
