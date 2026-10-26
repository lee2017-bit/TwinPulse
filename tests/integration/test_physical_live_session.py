# SPDX-License-Identifier: Apache-2.0
"""Supplementary device-free protocol/storage tests, not hardware acceptance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import base64
import io
import queue
import threading
import time
from threading import RLock
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.physical_live_session import PhysicalLiveSession,StreamEvidence,SCHEMA,reviewed_bundle
from twinpulse_app.physical_fleet_adapter import PhysicalFleetAdapter,PhysicalFleetServices
from twinpulse_app.robot_fleet import RobotFleet
from twinpulse_core.robot_control_timing import INPUT_TTL_S, INPUT_TTL_MS
from twinpulse_core.robot_battery import battery_display_config
from tests.integration import test_physical_fleet_adapter as fixtures


class PhysicalLiveSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=10.;self.wall=100.
        self.session=PhysicalLiveSession(ROOT,self.tmp.name,identity=Path('unused'),known_hosts=Path('unused'),
            process_factory=lambda *a,**k:self.fail('No SSH in supplementary tests'),clock=lambda:self.now,wall=lambda:self.wall)
        self.context=dict(operation_id=uuid4().hex,robot_id=uuid4().hex,project_id='project-a',connection_epoch=uuid4().hex,motion_epoch=uuid4().hex)
        self.session.context=dict(self.context,worker_sha256='a'*64)

    def test_start_requests_session_local_compression_without_auth_or_lifetime_changes(self):
        from twinpulse_app.robot_adapters import instance_binding
        identity=Path(self.tmp.name)/'identity';identity.touch()
        hosts=Path(self.tmp.name)/'known-hosts';hosts.touch()
        session=PhysicalLiveSession(ROOT,Path(self.tmp.name)/'archive',identity=identity,known_hosts=hosts,
            process_factory=lambda *a,**k:self.fail('No SSH in this construction test'))
        session.bind_instance(instance_binding(fixtures.PhysicalFleetAdapterTests.row('Local test','192.0.2.1')))
        captured=[]
        with patch('twinpulse_app.physical_live_session.shutil.which',return_value='ssh.exe'), \
                patch.object(session,'_run',side_effect=lambda argv,bundle:captured.append(argv)):
            session.start(self.context);session.thread.join(timeout=2)
        self.addCleanup(lambda:session.evidence.close(cleanup_confirmed=False))
        self.assertEqual(len(captured),1)
        command=captured[0]
        self.assertIn('-C',command)
        for fixed in ('BatchMode=yes','StrictHostKeyChecking=yes','IdentitiesOnly=yes','ForwardAgent=no',
                      'ClearAllForwardings=yes','ProxyCommand=none','ProxyJump=none',
                      # phys09 review: a Wi-Fi stall must be seen by ssh within ~30 s, not after the OS TCP timeout
                      'ServerAliveInterval=5','ServerAliveCountMax=6','TCPKeepAlive=yes'):
            self.assertIn(fixed,command)
        self.assertEqual(session.timing_values['input_ttl_ms'],INPUT_TTL_MS)

    def test_input_age_audit_binds_original_window_without_usable_nonce(self):
        self.heartbeat()
        self.session.evidence=StreamEvidence(Path(self.tmp.name)/'audit')
        self.addCleanup(lambda:self.session.evidence.close(cleanup_confirmed=False))
        window=self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='a'*24,watch_challenge='b'*24,motion_generation=1,issued_s=self.now)
        expected_sequence=window['sequence'];self.session.receive(window)
        self.session.command('drive',{'direction':'forward','sequence':1,'expires_at_ms':self.wall*1000+INPUT_TTL_MS},
            motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.session.evidence.close(cleanup_confirmed=False)
        records=[json.loads(line) for p in self.session.evidence.directory.glob('events-*.jsonl') for line in p.read_text().splitlines()]
        audit=next(row for row in records if row.get('schema')=='physical-live-pc-input-age-1.0')
        self.assertEqual(audit['window_robot_sequence'],expected_sequence)
        self.assertEqual(audit['window_robot_issued_s'],self.now)
        self.assertEqual(audit['challenge_fingerprint_sha256'],hashlib.sha256(('a'*24).encode()).hexdigest())
        self.assertNotIn('a'*24,json.dumps(audit))

    def event(self,kind='heartbeat',**data):
        return dict(schema=SCHEMA,**{k:self.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
            sequence=self.session.sequence+1,kind=kind,robot_monotonic_s=self.now,data=data)

    def heartbeat(self):
        self.session.receive(self.event(challenge='EPHEMERAL_NOT_TO_BE_ARCHIVED',motion_generation=1,
            boot_id='b'*32,release_id='c'*64,worker_sha256='a'*64,
            battery=dict(voltage_v=11.8,percent=None,source='measured',age_ms=50),control_state='READY',lidar_state='OFF'))
        request=uuid4().hex;self.session.watches[request]=self.now
        self.session.receive(self.event('command',action='watch',request_id=request,status='COMPLETED'))

    def test_green_requires_matching_current_heartbeat_not_process_or_history(self):
        self.assertFalse(self.session.snapshot()['live_heartbeat'])
        self.heartbeat();self.assertTrue(self.session.snapshot()['live_heartbeat'])
        self.now+=2.5
        self.assertFalse(self.session.snapshot()['live_heartbeat'])
        self.assertEqual(self.session.snapshot()['connection_state'],'DEGRADED')
        self.assertNotIn('challenge',self.session.events[0]['data'])

    def test_custom_presence_budget_bounds_ack_monitor_without_extending_input_lifetime(self):
        self.session.timing_values=dict(self.session.timing_values,operator_presence_ms=5000,
            input_ttl_ms=1000,output_timeout_ms=1200)
        self.heartbeat();self.now+=3.
        self.session.receive(self.event(**deepcopy(self.session.last)))
        current=self.session.snapshot()
        self.assertTrue(current['live_heartbeat'])
        self.assertEqual(current['heartbeat_freshness_ms'],5000)
        self.assertEqual(self.session.timing_values['input_ttl_ms'],1000)
        self.now+=2.001
        self.session.receive(self.event(**deepcopy(self.session.last)))
        self.assertFalse(self.session.snapshot()['live_heartbeat'])

    def motion(self,**changes):
        return dict(schema='robot-wheel-observation-1.0',state='OBSERVING',
            operation_id=self.context['operation_id'],robot_id=self.context['robot_id'],
            source_twin_context_id=None,motion_epoch=self.context['motion_epoch'],request_id='first-request',
            started_s=8.,result='NOT_ESTABLISHED',body_progress='UNKNOWN',**changes)

    def report_motion(self,observation):
        self.session.receive(self.event(boot_id='b'*32,release_id='c'*64,worker_sha256='a'*64,
            motion_observation=observation,last_control_fault={'reason':'ORIGINAL_FAILED_CHECK'}))

    def test_terminal_observation_without_final_heartbeat_projects_only_result_and_preserves_raw(self):
        for kind in ('command','control_pause','cleanup'):
            with self.subTest(kind=kind):
                observed=self.motion();self.report_motion(observed)
                original=deepcopy(self.session.last);at=self.session.at;watch=self.session.watch_ack_at
                ended={**observed,'state':'ENDED','ended_s':10.,'reason':'SESSION_CLOSED',
                    'result':'INCONCLUSIVE_BODY_MOTION','centre_m':.012}
                payload=({'action':'motion_observation','status':'ENDED','motion_observation':ended} if kind=='command' else
                    {'pause_id':'pause-'+kind,'reason':'OPERATOR_STOP','motion_observation':ended} if kind=='control_pause' else
                    {'subsystem':'session','confirmed':True,'control':{'motion_observation':ended}})
                self.session.receive(self.event(kind,**payload));ended['centre_m']=999
                self.session.closed=True;value=self.session.snapshot();self.session.closed=False
                self.assertEqual(value['motion_observation']['state'],'ENDED')
                self.assertEqual(value['motion_observation']['centre_m'],.012)
                self.assertEqual(value['last_control_fault'],{'reason':'ORIGINAL_FAILED_CHECK'})
                self.assertEqual(self.session.last,original);self.assertEqual(self.session.at,at)
                self.assertEqual(self.session.watch_ack_at,watch);self.assertFalse(value['live_heartbeat'])
                value['motion_observation']['centre_m']=888
                self.assertEqual(self.session.snapshot()['motion_observation']['centre_m'],.012)

    def test_old_heartbeat_cannot_reopen_ended_interval_and_new_gesture_is_not_overwritten(self):
        observed=self.motion();self.report_motion(observed)
        ended={**observed,'state':'ENDED','ended_s':10.,'reason':'OPERATOR_STOP','result':'INCONCLUSIVE_BODY_MOTION'}
        self.session.motion_epoch='new-pc-stop-epoch'
        self.session.receive(self.event('control_pause',pause_id='stop',reason='OPERATOR_STOP',motion_observation=ended))
        self.report_motion(observed)
        self.assertEqual(self.session.snapshot()['motion_observation']['state'],'ENDED')
        newer={**observed,'request_id':'second-request','started_s':11.}
        self.report_motion(newer)
        self.assertEqual(self.session.snapshot()['motion_observation']['request_id'],'second-request')
        self.assertEqual(self.session.snapshot()['motion_observation']['state'],'OBSERVING')
        self.session.receive(self.event('cleanup',subsystem='devices',control={'motion_observation':ended}))
        self.assertEqual(self.session.snapshot()['motion_observation']['request_id'],'second-request')

    def test_malformed_optional_observation_never_blocks_cleanup_or_changes_authority(self):
        observed=self.motion();self.report_motion(observed)
        for invalid in ({'operation_id':'other'},{'source_twin_context_id':'wrong-twin'},
                        {'ended_s':float('nan')},{'started_s':100.},{'request_id':None},
                        {'state':[]},{'state':{}},{'started_s':10**1000},{'ended_s':10**1000}):
            ended={**observed,'state':'ENDED','ended_s':10.,'result':'INCONCLUSIVE_BODY_MOTION',**invalid}
            self.session.receive(self.event('cleanup',subsystem='session',confirmed=True,control={'motion_observation':ended}))
            self.assertTrue(self.session.cleanup_confirmed)
            self.assertEqual(self.session.snapshot()['motion_observation']['state'],'OBSERVING')
            self.assertFalse(self.session.snapshot()['live_heartbeat'])
            self.assertIsNotNone(self.session.snapshot().get('motion_observation_projection_error'))
        for subsystem in ([],{}):
            self.session.receive(self.event('cleanup',subsystem=subsystem,control={'motion_observation':[]}))
        for state in ([],{}):
            self.report_motion({**observed,'state':state})
            self.assertNotIn('motion_observation',self.session.snapshot())

    def test_slow_display_copy_cannot_hold_stop_admission_lock(self):
        self.heartbeat();self.session.last['large_display']={'rows':[[1,2]]}
        entered=Event();release=Event();stopped=Event();original=deepcopy;errors=[]
        def copying(value,*args,**kwargs):
            if isinstance(value,dict) and 'large_display' in value:
                entered.set();release.wait(2)
            return original(value,*args,**kwargs)
        def stop():
            try:self.session.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
            except Exception as error:errors.append(error)
            finally:stopped.set()
        with patch('twinpulse_app.physical_live_session.deepcopy',side_effect=copying):
            reader=threading.Thread(target=self.session.snapshot,daemon=True);reader.start()
            self.assertTrue(entered.wait(1));writer=threading.Thread(target=stop,daemon=True);writer.start()
            try:completed=stopped.wait(.2)
            finally:release.set();reader.join(1);writer.join(1)
        self.assertTrue(completed,'Display copy held the Stop/input admission lock')
        self.assertEqual(errors,[]);self.assertEqual(self.session.writes.get_nowait()['action'],'stop')

    def test_incoming_report_and_public_snapshot_do_not_alias(self):
        self.heartbeat();row=self.event(scan_state={'rows':[[1,2]]},boot_id='b'*32,release_id='c'*64,worker_sha256='a'*64)
        self.session.receive(row);row['data']['scan_state']['rows'][0][0]=999
        result=self.session.snapshot();result['scan_state']['rows'][0][0]=888
        self.assertEqual(self.session.snapshot()['scan_state']['rows'],[[1,2]])

    def test_large_recording_manifest_copy_cannot_hold_stop_admission_lock(self):
        self.heartbeat();entered=Event();release=Event();stopped=Event()
        def report():entered.set();release.wait(2);return {'segments':[]}
        self.session.evidence=SimpleNamespace(snapshot=report,error=None)
        reader=threading.Thread(target=self.session.snapshot,daemon=True);reader.start()
        self.assertTrue(entered.wait(1))
        writer=threading.Thread(target=lambda:(self.session.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex),stopped.set()),daemon=True)
        writer.start()
        try:completed=stopped.wait(.2)
        finally:release.set();reader.join(1);writer.join(1)
        self.assertTrue(completed,'Recording manifest copy held Stop/input admission lock')

    def test_closed_session_never_reports_streaming_scan_or_current_diagnostic(self):
        self.heartbeat();self.session.last.update(lidar_state='STREAMING',
            telemetry_diagnostic=dict(reason='CURRENT',source_age_s=.01))
        self.session.scan=dict(points=[[1,2]],source='original');self.session.scan_at=self.now
        self.session.closed=True;self.session.cleanup_confirmed=False
        value=self.session.snapshot()
        self.assertEqual(value['lidar_state'],'FAULT');self.assertIsNone(value['scan'])
        self.assertEqual(value['last_reported_lidar_state'],'STREAMING')
        self.assertEqual(value['telemetry_diagnostic']['reason'],'SESSION_CLOSED_HISTORICAL')
        self.assertIsNone(value['telemetry_diagnostic']['source_age_s']);self.assertFalse(value['live_heartbeat'])
        self.session.cleanup_confirmed=True;self.assertEqual(self.session.snapshot()['lidar_state'],'OFF')

    def test_link_detail_explains_every_non_connected_state_for_the_operator(self):
        self.session.context=None
        value=self.session.snapshot()
        self.assertEqual((value['connection_state'],value['link_detail'],value['control_owner_state']),('DEGRADED','no session context',None))
        self.session.context=dict(self.context,worker_sha256='a'*64)
        value=self.session.snapshot()
        self.assertEqual((value['connection_state'],value['link_detail']),('CONNECTING','waiting for the first heartbeat'))
        self.heartbeat()
        value=self.session.snapshot()
        self.assertEqual((value['connection_state'],value['link_detail'],value['control_owner_state']),('CONNECTED',None,'ACTIVE'))
        self.assertEqual(value['lidar_state_source'],'robot');self.assertIsNone(value['robot_storage'])
        self.now+=2.5
        value=self.session.snapshot()
        self.assertEqual((value['connection_state'],value['link_detail']),('DEGRADED','no fresh heartbeat for 2500 ms (limit 2500 ms)'))
        self.session.receive(self.event(**deepcopy(self.session.last)))  # fresh heartbeat, stale watch reply
        value=self.session.snapshot()
        self.assertEqual((value['connection_state'],value['link_detail']),
                         ('DEGRADED','watch round-trip slower than 500 ms or no watch reply within 2500 ms'))
        self.session.closed=True;self.session.error='REMOTE_EXIT_WITHOUT_CLEANUP'
        self.session.remote_stderr_tail='FLEET_WORKER_REJECTED:OSError:ENOSPC:No space left on device:/home/ubuntu/x'
        value=self.session.snapshot()
        self.assertEqual(value['connection_state'],'DISCONNECTED')
        self.assertEqual(value['link_detail'],'REMOTE_EXIT_WITHOUT_CLEANUP · FLEET_WORKER_REJECTED:OSError:ENOSPC:No space left on device:/home/ubuntu/x')
        self.assertEqual(value['remote_stderr_tail'],self.session.remote_stderr_tail)
        self.assertIsNone(value['control_owner_state'])
        self.assertEqual((value['lidar_state'],value['lidar_state_source'],value['last_reported_lidar_state']),('FAULT','pc_after_exit','OFF'))

    def test_robot_recording_fault_marks_the_control_owner_exited_while_the_link_is_still_up(self):
        self.heartbeat()
        storage=dict(free_bytes=100*1024*1024,reserve_bytes=512*1024*1024,state='LOW')
        self.session.receive(self.event(**dict(deepcopy(self.session.last),blockers=['RECORDING_INCOMPLETE'],drive_ready=False,
            recording_failure_reason='SESSION_DISK_LOW',storage=storage)))
        value=self.session.snapshot()
        self.assertEqual(value['connection_state'],'CONNECTED')
        self.assertEqual(value['control_owner_state'],'EXITED_RECONNECT_REQUIRED')
        self.assertEqual(value['recording_failure_reason'],'SESSION_DISK_LOW')
        self.assertEqual(value['robot_storage'],storage);self.assertFalse(value['drive_ready'])
        # Terminal cleanup carries the reason when the last heartbeat did not.
        self.session.receive(self.event(**dict(deepcopy(self.session.last),blockers=[],recording_failure_reason=None,storage=None)))
        self.assertEqual(self.session.snapshot()['control_owner_state'],'ACTIVE')
        self.session.receive(self.event('cleanup',subsystem='session',confirmed=True,recording_complete=False,
            recording_failure_reason='SESSION_JOURNAL_APPEND_REJECTED'))
        value=self.session.snapshot()
        self.assertEqual(value['recording_failure_reason'],'SESSION_JOURNAL_APPEND_REJECTED')
        self.assertEqual(value['control_owner_state'],'EXITED_RECONNECT_REQUIRED')

    def test_stderr_tail_is_the_last_lines_bounded_and_printable(self):
        from twinpulse_app.physical_live_session import stderr_tail
        path=Path(self.tmp.name)/'ssh-stderr.log'
        self.assertIsNone(stderr_tail(path))
        path.write_bytes(b'');self.assertIsNone(stderr_tail(path))
        path.write_bytes(b'\n  \n')
        self.assertIsNone(stderr_tail(path))
        rejected=b'FLEET_WORKER_REJECTED:OSError:ENOSPC:No space left on device:/home/ubuntu/s\x1b[0m'
        path.write_bytes(b'x'*5000+b'\nWarning: Permanently added\n\n'+rejected+b'\n\n')
        tail=stderr_tail(path)
        self.assertTrue(tail.endswith('FLEET_WORKER_REJECTED:OSError:ENOSPC:No space left on device:/home/ubuntu/s?[0m'),tail)
        self.assertIn('Warning: Permanently added | FLEET_WORKER_REJECTED',tail)
        self.assertLessEqual(len(tail),600);self.assertNotIn('\n',tail)
        self.assertEqual(len(stderr_tail(path,limit=40)),40)
        path.write_bytes(b'FLEET_WORKER_CLEANUP:{"confirmed":false,"reason":"SESSION_DISK_LOW"}\n')
        self.assertEqual(stderr_tail(path),'FLEET_WORKER_CLEANUP:{"confirmed":false,"reason":"SESSION_DISK_LOW"}')

    def test_reported_incomplete_cleanup_is_not_a_missing_ack_or_complete_record(self):
        self.session.receive(self.event('cleanup',subsystem='session',confirmed=False,recording_complete=True,
            control=dict(cleanup=dict(cleanup_confirmed=True),field_evidence=dict(complete=False,error='FIELD_EVIDENCE_STALLED'))))
        self.session._classify_remote_exit(2)
        snapshot=self.session.snapshot()
        self.assertTrue(snapshot['terminal_cleanup_received']);self.assertFalse(snapshot['cleanup_confirmed'])
        self.assertEqual(snapshot['transport_error'],'REMOTE_CLEANUP_REPORTED_INCOMPLETE')
        self.assertEqual(snapshot['remote_exit_code'],2)
        self.assertEqual(snapshot['terminal_cleanup']['control']['field_evidence']['error'],'FIELD_EVIDENCE_STALLED')

    def test_missing_terminal_ack_still_reports_missing_cleanup(self):
        self.session._classify_remote_exit(2)
        self.assertEqual(self.session.error,'REMOTE_EXIT_WITHOUT_CLEANUP')
        self.assertFalse(self.session.snapshot()['terminal_cleanup_received'])

    def test_other_project_robot_connection_sequence_and_nonfinite_rejected(self):
        for field in ('project_id','robot_id','connection_epoch','operation_id'):
            event=self.event();event[field]='other'
            with self.assertRaisesRegex(ValueError,'IDENTITY'):self.session.receive(event)
        event=self.event();event['sequence']=2
        with self.assertRaisesRegex(ValueError,'SEQUENCE'):self.session.receive(event)
        event=self.event();event['robot_monotonic_s']=float('nan')
        with self.assertRaisesRegex(ValueError,'SHAPE'):self.session.receive(event)

    def test_actual_payload_expiry_and_original_lineage_reach_transport_queue(self):
        self.heartbeat()
        request=uuid4().hex
        self.session.command('drive',dict(direction='backward',sequence=7,expires_at_ms=100200),
            motion_epoch=self.context['motion_epoch'],request_id=request)
        packet=self.session.writes.get_nowait()
        self.assertEqual(packet['payload']['direction'],'backward')
        self.assertEqual(packet['payload']['expires_at_ms'],100200)
        self.assertEqual(packet['payload']['source_age_ms'],INPUT_TTL_MS-200)
        for key in ('robot_id','operation_id','project_id','connection_epoch','motion_epoch'):self.assertEqual(packet[key],self.context[key])
        self.assertEqual(packet['request_id'],request)
        with self.assertRaises(BrokerError):self.session.command('drive',dict(direction='forward',sequence=8,expires_at_ms=100000),
            motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.assertTrue(self.session.writes.empty())

    def test_small_current_input_window_replies_before_next_display_heartbeat(self):
        self.heartbeat();self.session.motion_epoch=self.context['motion_epoch']
        self.now+=.06
        window=self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='1'*24,watch_challenge='2'*24,motion_generation=2,issued_s=self.now-.01)
        self.session.receive(window)
        packet=self.session.writes.get_nowait()
        self.assertEqual(packet['action'],'watch')
        self.assertEqual(packet['payload']['challenge'],'2'*24)
        self.assertEqual(packet['payload']['motion_generation'],2)
        # Late full telemetry cannot replace the newer control nonce.
        self.heartbeat()
        self.session.command('drive',dict(direction='forward',expires_at_ms=100250),
            motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        drive=self.session.writes.get_nowait()
        self.assertEqual(drive['payload']['challenge'],'1'*24)
        self.assertEqual(drive['payload']['motion_generation'],2)
        self.assertFalse(any('challenge' in e['data'] or 'watch_challenge' in e['data'] for e in self.session.events))

    def test_small_window_deducts_only_the_pc_age_already_inside_nonce_roundtrip(self):
        self.heartbeat()
        self.session.receive(self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='1'*24,watch_challenge='2'*24,motion_generation=1,issued_s=self.now-.01))
        self.session.writes.get_nowait() # Independent presence watch, not drive.
        self.now+=.09;self.wall+=.09
        recorded=[]
        self.session.evidence=SimpleNamespace(error=None,append=lambda raw:recorded.append(json.loads(raw)) or True)
        expires=self.wall*1000+INPUT_TTL_MS-140
        self.session.command('drive',dict(direction='forward',expires_at_ms=expires),
            motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        packet=self.session.writes.get_nowait()
        self.assertEqual(packet['payload']['expires_at_ms'],expires)
        self.assertAlmostEqual(packet['payload']['source_age_ms'],50.,places=6)
        audit=recorded[-1]
        self.assertEqual(audit['schema'],'physical-live-pc-input-age-1.0')
        self.assertEqual(audit['ui_age_ms'],140.)
        self.assertAlmostEqual(audit['deducted_overlap_ms'],90.,places=6)
        self.assertEqual(audit['basis'],'SAME_SMALL_WINDOW_PC_OVERLAP')
        self.assertFalse(audit['execution_confirmed']);self.assertNotIn('challenge',audit)
        self.assertNotIn('ui_age_ms',packet['payload']) # Worker wire stays unchanged.

    def test_small_window_caps_correction_at_nonce_and_never_accepts_expired_ui_input(self):
        self.heartbeat()
        self.session.receive(self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='1'*24,watch_challenge='2'*24,motion_generation=1,issued_s=self.now))
        self.session.writes.get_nowait()
        self.now+=.09;self.wall+=.09
        self.session.command('drive',dict(direction='forward',expires_at_ms=self.wall*1000+INPUT_TTL_MS-20),
            motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.assertEqual(self.session.writes.get_nowait()['payload']['source_age_ms'],0.)
        with self.assertRaisesRegex(BrokerError,'expired'):
            self.session.command('drive',dict(direction='forward',expires_at_ms=self.wall*1000),
                motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)

    def test_corrected_nonce_bound_is_never_newer_than_real_ui_creation_or_nonce_issuance(self):
        for ui_age_ms in (0.,20.,140.,INPUT_TTL_MS-1.):
            for local_since_receipt_ms in (0.,10.,90.,249.):
                for robot_to_pc_ms in (0.,15.,90.):
                    issued=10.
                    created_bound=issued-max(0.,ui_age_ms-local_since_receipt_ms)/1000
                    actual_created=issued+(robot_to_pc_ms+local_since_receipt_ms-ui_age_ms)/1000
                    self.assertLessEqual(created_bound,actual_created+1e-12)
                    self.assertLessEqual(created_bound,issued)
        # An old input before a new window is still old; overlap is not a
        # permission to grant a full new lifetime at enqueue or delivery.
        created=10.-max(0.,INPUT_TTL_MS-10.-10.)/1000
        self.assertGreater((10.04-created)*1000,INPUT_TTL_MS)

    def test_failed_input_age_recording_queues_no_drive(self):
        self.heartbeat()
        self.session.evidence=SimpleNamespace(error=None,append=lambda _:False)
        with self.assertRaisesRegex(BrokerError,'evidence'):
            self.session.command('drive',dict(direction='forward',expires_at_ms=100250),
                motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.assertTrue(self.session.writes.empty())

    def test_small_input_window_cannot_resume_after_close_or_presence_fault(self):
        self.heartbeat();self.session.motion_epoch=self.context['motion_epoch']
        self.session.presence_gap_until=self.now+.7
        self.session.receive(self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='1'*24,watch_challenge='2'*24,motion_generation=2,issued_s=self.now))
        self.assertTrue(self.session.writes.empty())
        self.session.closing=True;self.now+=.8
        self.session.receive(self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='3'*24,watch_challenge='4'*24,motion_generation=3,issued_s=self.now))
        self.assertTrue(self.session.writes.empty())

    def test_small_input_window_rejects_old_issue_and_wrong_session(self):
        self.heartbeat()
        event=self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='1'*24,watch_challenge='2'*24,motion_generation=2,issued_s=self.now-INPUT_TTL_S-.001)
        with self.assertRaisesRegex(ValueError,'INPUT_WINDOW'):self.session.receive(event)
        event=self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='1'*24,watch_challenge='2'*24,motion_generation=2,issued_s=self.now)
        event['operation_id']='other'
        with self.assertRaisesRegex(ValueError,'IDENTITY'):self.session.receive(event)
        self.assertTrue(self.session.writes.empty())

    def test_stop_discards_queued_drives_even_stale_heartbeat_and_watch_cannot_drive(self):
        self.heartbeat()
        for i in range(4):self.session.command('drive',dict(direction='forward',sequence=i+1,expires_at_ms=100250),motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.now+=10
        self.session.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
        self.assertEqual(self.session.writes.qsize(),1)
        self.assertEqual(self.session.writes.get_nowait()['action'],'stop')
        with self.assertRaises(BrokerError):self.session.command('task',dict(direction='left',amount=1),motion_epoch=uuid4().hex,request_id=uuid4().hex)

    def test_same_nonce_is_reserved_once_and_pending_hold_keeps_original_expiry(self):
        self.heartbeat()
        first,second=uuid4().hex,uuid4().hex
        payload=dict(direction='forward',expires_at_ms=100250)
        self.session.command('drive',payload,motion_epoch=self.context['motion_epoch'],request_id=first)
        self.session.writes.get_nowait()
        result=self.session.command('drive',payload,motion_epoch=self.context['motion_epoch'],request_id=second)
        self.assertEqual(result['status'],'pending_input_window');self.assertTrue(self.session.writes.empty())
        self.now+=.05;self.wall+=.05
        self.session.receive(self.event('command',action='input_window',schema='robot-input-window-1.0',
            challenge='1'*24,watch_challenge='2'*24,motion_generation=1,issued_s=self.now))
        drive=self.session.writes.get_nowait()
        self.assertEqual(drive['request_id'],second);self.assertEqual(drive['payload']['expires_at_ms'],100250)
        self.assertAlmostEqual(drive['payload']['source_age_ms'],INPUT_TTL_MS-200)
        self.assertEqual(drive['payload']['challenge'],'1'*24)
        self.assertIsNone(self.session.pending_drive)

    def test_reviewed_guard_bundle_retains_vendor_build_license_and_parent_binding(self):
        _,encoded,_=reviewed_bundle(ROOT)
        files=json.loads(encoded)['files']
        for name in ('guard_runtime.py','owned_exec.py','guard_base/package.xml','guard_base/LICENSE','guard_base/NOTICE',
                     'guard_base/CMakeLists.txt','include/twinpulse_robot_safety/ros_guard.hpp','tests/ros_guard_test.cpp'):
            self.assertTrue(name in files,name)
        owned=base64.b64decode(files['owned_exec.py']['base64'])
        self.assertIn(b'reviewed-base',owned)
        self.assertIn(b'prctl',owned)

    def test_pending_hold_does_not_cross_stop_expiry_or_robot_generation(self):
        for barrier in ('stop','expiry','generation'):
            with self.subTest(barrier=barrier):
                # Reset only local protocol state; no hardware or saved project.
                self.heartbeat();self.session.used_input_challenges.clear();self.session.motion_epoch=self.context['motion_epoch']
                payload=dict(direction='forward',expires_at_ms=100250)
                for _ in range(2):self.session.command('drive',payload,motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
                self.session.writes.get_nowait()
                if barrier=='stop':
                    self.session.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
                    self.session.writes.get_nowait()
                if barrier=='expiry':self.wall=100.3
                self.session.receive(self.event('command',action='input_window',schema='robot-input-window-1.0',
                    challenge='3'*24,watch_challenge='4'*24,motion_generation=2 if barrier=='generation' else 1,issued_s=self.now))
                packets=[]
                while not self.session.writes.empty():packets.append(self.session.writes.get_nowait())
                self.assertFalse(any(p['action']=='drive' for p in packets));self.assertIsNone(self.session.pending_drive)
                self.session.input_window=None;self.session.input_window_at=None;self.wall=100.

    def test_robot_pause_fences_old_http_gesture_before_new_nonce_and_does_not_loop_on_stop(self):
        self.heartbeat();old=self.context['motion_epoch']
        for _ in range(2):self.session.command('drive',dict(direction='forward',expires_at_ms=100250),motion_epoch=old,request_id=uuid4().hex)
        self.session.receive(self.event('control_pause',pause_id='connection:1',reason='INPUT_DEADLINE_EXPIRED',motion_generation=2))
        new=self.session.motion_epoch;self.assertNotEqual(old,new);self.assertIsNone(self.session.pending_drive)
        self.assertEqual(self.session.writes.qsize(),1);self.assertEqual(self.session.writes.get_nowait()['action'],'stop')
        with self.assertRaisesRegex(BrokerError,'generation changed'):
            self.session.command('drive',dict(direction='forward',expires_at_ms=100250),motion_epoch=old,request_id=uuid4().hex)
        self.session.receive(self.event('control_pause',pause_id='connection:2',reason='OPERATOR_STOP',motion_generation=3))
        self.assertEqual(self.session.motion_epoch,new);self.assertTrue(self.session.writes.empty())
        self.assertEqual(self.session.snapshot()['pc_motion_epoch'],new)

    def test_idle_profile_pause_preserves_queued_field_setup_without_granting_motion(self):
        self.heartbeat()
        self.session.command('field_setup',{'config':{}},motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.session.receive(self.event('control_pause',pause_id='connection:profile',reason='PROFILE_CHANGED',motion_generation=1))
        self.assertEqual(self.session.writes.qsize(),1)
        self.assertEqual(self.session.writes.get_nowait()['action'],'field_setup')
        self.assertFalse(self.session.authority_requested)

    def test_zero_motion_collection_pause_does_not_cancel_its_own_request(self):
        for case in ('stationary','soak'):
            with self.subTest(case=case):
                self.heartbeat();self.session.used_input_challenges.clear()
                epoch=self.context['motion_epoch'];self.session.motion_epoch=epoch
                request=uuid4().hex
                self.session.command('field_test',dict(case=case,confirmed=True),motion_epoch=epoch,request_id=request)
                self.assertFalse(self.session.authority_requested)
                self.session.receive(self.event('control_pause',pause_id=uuid4().hex,
                    reason='FIELD_ZERO_MOTION_COLLECTION',motion_generation=2))
                packet=self.session.writes.get_nowait()
                self.assertEqual(packet['action'],'field_test');self.assertEqual(packet['request_id'],request)
                self.assertTrue(self.session.writes.empty());self.assertEqual(self.session.motion_epoch,epoch)

    def test_motion_field_tests_and_prior_gesture_keep_the_pause_stop_fence(self):
        for case,prior in (('bootstrap_stop',False),('forward',False),('full_turn',False),('stationary',True),('soak',True)):
            with self.subTest(case=case,prior_gesture=prior):
                self.heartbeat();self.session.used_input_challenges.clear()
                epoch=self.context['motion_epoch'];self.session.motion_epoch=epoch
                self.session.authority_requested=prior
                self.session.command('field_test',dict(case=case,confirmed=True),motion_epoch=epoch,request_id=uuid4().hex)
                self.assertTrue(self.session.authority_requested)
                self.session.receive(self.event('control_pause',pause_id=uuid4().hex,
                    reason='FIELD_ZERO_MOTION_COLLECTION' if prior else 'INPUT_DEADLINE_EXPIRED',motion_generation=3))
                self.assertNotEqual(self.session.motion_epoch,epoch)
                self.assertEqual(self.session.writes.get_nowait()['action'],'stop')
                self.assertTrue(self.session.writes.empty());self.assertFalse(self.session.authority_requested)

    def test_zero_motion_collection_never_clears_pending_drive_stop_fence(self):
        self.heartbeat();epoch=self.context['motion_epoch'];self.session.motion_epoch=epoch
        self.session.pending_drive=dict(request_id=uuid4().hex)
        self.session.command('field_test',dict(case='stationary',confirmed=True),motion_epoch=epoch,request_id=uuid4().hex)
        self.assertIsNotNone(self.session.pending_drive)
        self.session.receive(self.event('control_pause',pause_id=uuid4().hex,
            reason='FIELD_ZERO_MOTION_COLLECTION',motion_generation=2))
        self.assertIsNone(self.session.pending_drive)
        self.assertEqual(self.session.writes.get_nowait()['action'],'stop')

    def test_explicit_stop_still_cancels_zero_motion_collection_without_loop(self):
        self.heartbeat();epoch=self.context['motion_epoch']
        self.session.command('field_test',dict(case='stationary',confirmed=True),motion_epoch=epoch,request_id=uuid4().hex)
        stop=uuid4().hex
        self.session.command('stop',{},motion_epoch=uuid4().hex,request_id=stop)
        packet=self.session.writes.get_nowait()
        self.assertEqual(packet['action'],'stop');self.assertEqual(packet['request_id'],stop)
        self.session.receive(self.event('control_pause',pause_id=uuid4().hex,reason='OPERATOR_STOP',motion_generation=3))
        self.assertTrue(self.session.writes.empty());self.assertFalse(self.session.authority_requested)

    def test_continuous_ten_hz_writer_keeps_matching_watch_ack_and_ack_loss_degrades(self):
        """Real session threads, injected local pipes only; no SSH or robot."""
        session=self.session;session.clock=time.monotonic;session.wall=time.time
        session.motion_epoch=self.context['motion_epoch']
        session.evidence=StreamEvidence(Path(self.tmp.name)/'pipe-recording')
        class PipeProcess:
            def __init__(self):
                self.stdin=self;self.stdout=self;self.stderr=io.BytesIO()
                self.lines=queue.Queue();self.lock=RLock();self.sequence=0
                self.stopped=Event();self.acknowledge=True;self.commands=[]
            def event(self,kind,data):
                with self.lock:
                    self.sequence+=1
                    event=dict(schema=SCHEMA,**{k:session.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                        sequence=self.sequence,kind=kind,robot_monotonic_s=time.monotonic(),data=data)
                    self.lines.put((json.dumps(event)+'\n').encode())
            def heartbeat(self):
                while not self.stopped.wait(.05):
                    nonce=uuid4().hex
                    self.event('heartbeat',dict(challenge='motor-'+nonce,watch_challenge='presence-'+nonce,motion_generation=1,
                        boot_id='b'*32,release_id='c'*64,worker_sha256='a'*64,lidar_state='OFF'))
            def write(self,raw):
                value=json.loads(raw)
                if 'action' not in value:return len(raw)
                # A bounded pipe delay leaves <100ms idle between 10Hz inputs.
                time.sleep(.025)
                self.commands.append(deepcopy(value))
                if value['action']=='watch' and self.acknowledge:
                    self.event('command',dict(action='watch',request_id=value['request_id'],status='COMPLETED'))
                if value['action']=='close':
                    self.event('cleanup',dict(subsystem='session',confirmed=True));self.close()
                return len(raw)
            def flush(self):pass
            def readline(self,_):return self.lines.get(timeout=3)
            def close(self):
                if not self.stopped.is_set():self.stopped.set();self.lines.put(b'')
            terminate=close
            kill=close
            def poll(self):return 0 if self.stopped.is_set() else None
            def wait(self,timeout):self.stopped.wait(timeout);return 0
        process=PipeProcess();session.factory=lambda *a,**k:process
        session.thread=threading.Thread(target=session._run,args=(['injected-no-transport'],b'{}\n'),daemon=True)
        pulse=threading.Thread(target=process.heartbeat,daemon=True)
        sending=Event();producer_errors=[]
        def produce():
            sequence=0
            while not sending.wait(.1):
                sequence+=1
                try:session.command('drive',dict(direction='forward',sequence=sequence,expires_at_ms=time.time()*1000+INPUT_TTL_MS),
                    motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
                except Exception as error:producer_errors.append(error);break
        producer=threading.Thread(target=produce,daemon=True)
        try:
            session.thread.start();pulse.start()
            end=time.monotonic()+1
            while session.at is None and time.monotonic()<end:time.sleep(.01)
            producer.start()
            time.sleep(3.1)
            self.assertFalse(producer_errors)
            self.assertTrue(session.snapshot()['live_heartbeat'],session.snapshot())
            watches=[c for c in process.commands if c['action']=='watch']
            self.assertGreaterEqual(len(watches),20)
            self.assertTrue(all(c['payload']['challenge'].startswith('presence-') for c in watches))
            self.assertEqual(len({c['payload']['challenge'] for c in watches}),len(watches))
            process.acknowledge=False
            time.sleep(2.7)
            value=session.snapshot()
            self.assertLess(value['telemetry_age_ms'],250)
            self.assertFalse(value['live_heartbeat']);self.assertEqual(value['connection_state'],'DEGRADED')
            self.assertFalse(producer_errors)
            sequences=[c['sequence'] for c in process.commands]
            self.assertEqual(sequences,sorted(set(sequences)))
            drives=[c for c in process.commands if c['action']=='drive']
            self.assertGreaterEqual(len(drives),50)
            self.assertTrue(all(c['payload']['source_age_ms']<25 for c in drives))
        finally:
            sending.set()
            if producer.ident:producer.join(1)
            session.close();process.close();pulse.join(1)
        self.assertTrue(session.cleanup_confirmed)
        self.assertEqual(process.commands[-1]['action'],'close')

    def test_sensor_acquisition_metadata_is_not_replaced_with_pc_scan_receipt(self):
        frame=dict(source='physical_native_sensor_unaligned',age_ms=17,age_basis='serial_receipt',complete=False,
            nodes_sha256='d'*64,acquisition_timing=dict(basis='serial_receipt_unqualified',acquisition_earliest_s=None))
        self.session.receive(self.event(boot_id='b'*32,release_id='c'*64,worker_sha256='a'*64,sensor_frame=frame))
        self.session.receive(self.event('scan',points=[[1,0]],source='physical_native_sensor_unaligned'))
        self.now+=.1
        result=self.session.snapshot()
        self.assertEqual(result['sensor_frame'],frame)
        self.assertAlmostEqual(result['scan_receipt']['age_ms'],100)
        self.assertEqual(result['scan_receipt']['age_basis'],'pc_scan_receipt')
        self.assertFalse(result['scan_receipt']['aligned'])

    def test_cleanup_requires_explicit_confirmed_true_not_exit_or_subsystem_receipt(self):
        self.session.receive(self.event('cleanup',subsystem='sensor'))
        self.assertFalse(self.session.cleanup_confirmed)
        self.session.receive(self.event('cleanup',subsystem='other',confirmed=True))
        self.assertFalse(self.session.cleanup_confirmed)
        self.session.receive(self.event('cleanup',subsystem='session',confirmed=True))
        self.assertTrue(self.session.cleanup_confirmed)

    def test_terminal_close_is_not_removed_by_later_stop_or_duplicate_close(self):
        self.heartbeat();request=uuid4().hex
        self.session.command('close',{},motion_epoch=uuid4().hex,request_id=request)
        for action in ('stop','close','stop'):
            result=self.session.command(action,{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
            self.assertEqual(result.get('coalesced_with_close_request_id'),request)
        self.assertEqual(self.session.writes.qsize(),1)
        pending=self.session.writes.get_nowait()
        self.assertEqual(pending['action'],'close');self.assertEqual(pending['request_id'],request)
        with self.assertRaisesRegex(BrokerError,'Disconnect is already'):
            self.session.command('watch',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)

    def test_raw_events_do_not_fill_recent_ui_memory_and_invalid_scan_is_rejected(self):
        self.session.receive(self.event('raw',base64='AA==',offset=0))
        for data in (dict(schema='physical-live-source-1.0',kind='chunk',base64='AA==',offset=0),
                     dict(schema='physical-live-source-1.0',kind='manifest',members=[],complete=False)):
            event=self.event('raw_source');event['data']=data;self.session.receive(event)
        self.assertFalse(self.session.events)
        self.assertFalse(self.session.snapshot()['source_export']['complete'])
        with self.assertRaisesRegex(ValueError,'SCAN_SHAPE'):self.session.receive(self.event('scan',points=[[float('inf'),0]]))

    def test_segmented_original_bytes_and_cleanup_completeness(self):
        evidence=StreamEvidence(Path(self.tmp.name)/'segments',segment_bytes=20,maximum_bytes=80)
        chunks=[b'{"sample":1}\n',b'{"sample":2}\n',b'{"sample":3}\n']
        for raw in chunks:self.assertTrue(evidence.append(raw))
        receipt=evidence.close(cleanup_confirmed=True)
        self.assertTrue(receipt['complete']);self.assertEqual(len(receipt['segments']),3)
        for row,raw in zip(receipt['segments'],chunks):
            self.assertEqual((evidence.directory/row['path']).read_bytes(),raw)
            self.assertEqual(row['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertFalse(evidence.append(b'late\n'))
        other=StreamEvidence(Path(self.tmp.name)/'unknown')
        self.assertFalse(other.close(cleanup_confirmed=False)['complete'])

    def test_capacity_error_retains_existing_evidence_and_no_complete_receipt(self):
        evidence=StreamEvidence(Path(self.tmp.name)/'bounded',segment_bytes=20,maximum_bytes=20)
        self.assertTrue(evidence.append(b'{"sample":1}\n'))
        self.assertFalse(evidence.append(b'{"sample":2}\n'))
        receipt=evidence.close(cleanup_confirmed=True)
        self.assertFalse(receipt['complete'])
        self.assertIn('CAPACITY',receipt['error'])
        self.assertEqual((evidence.directory/receipt['segments'][0]['path']).read_bytes(),b'{"sample":1}\n')

    def test_shipped_bundle_import_closure_in_isolated_python_and_start_rejection(self):
        sha,encoded,digests=reviewed_bundle(ROOT)
        packet=json.loads(encoded)
        stage=Path(self.tmp.name)/'shipped-only';stage.mkdir()
        for name,item in packet['files'].items():
            data=base64.b64decode(item['base64'],validate=True)
            self.assertEqual(hashlib.sha256(data).hexdigest(),digests[name])
            path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        # -I rejects accidental access to repository imports/PYTHONPATH; module
        # import and invalid context must touch no serial/ROS/current release.
        code="import sys;sys.path.insert(0,sys.argv[1]);import fleet_worker;print('SHIPPED_IMPORT_OK');" \
             "\ntry:fleet_worker.checked_context({})\nexcept ValueError as e:print(str(e))\nelse:raise AssertionError('Invalid start accepted')"
        child=subprocess.run([sys.executable,'-I','-B','-c',code,str(stage)],capture_output=True,text=True,timeout=15)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(child.stdout.splitlines(),['SHIPPED_IMPORT_OK','START_SHAPE'])

    def test_stalled_disk_fsync_does_not_hold_snapshot_or_stop_admission(self):
        entered=Event();release=Event()
        def fsync(_):entered.set();release.wait(2)
        evidence=StreamEvidence(Path(self.tmp.name)/'stalled',segment_bytes=20)
        self.session.evidence=evidence
        try:
            with patch('twinpulse_app.physical_live_session.os.fsync',fsync):
                evidence.append(b'{"sample":1}\n');evidence.append(b'{"sample":2}\n')
                self.assertTrue(entered.wait(1))
                started=__import__('time').monotonic()
                self.session.snapshot()
                self.session.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
                self.assertLess(__import__('time').monotonic()-started,.1)
                self.assertEqual(self.session.writes.get_nowait()['action'],'stop')
                release.set();self.assertTrue(evidence.close(cleanup_confirmed=True)['complete'])
        finally:release.set();evidence.close(cleanup_confirmed=True)


class FleetPhysicalEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.trace=[];self.row=fixtures.PhysicalFleetAdapterTests.row('Actual binding under offline test','192.0.2.1')
        self.devices=SimpleNamespace(registry_service=SimpleNamespace(registry=SimpleNamespace(
            registration_snapshot=lambda:dict(robots=[deepcopy(self.row)]),
            registered=lambda identity:deepcopy(self.row) if identity==self.row['id'] else None,
            battery_display_for_view=lambda identity,binding:deepcopy(self.row.get('battery_display',battery_display_config('robotis_opencr'))))),
            lock=RLock(),closed=False,contexts=[],diagnostics=fixtures.Diagnostics('legacy',self.trace),readiness=fixtures.Readiness('legacy',self.trace),controller=fixtures.Controller('legacy',self.trace))
        from twinpulse_core.robot_timing_profile import profile as timing_profile
        from twinpulse_app.robot_adapters import instance_binding
        self.devices.registry_service.registry.timing_store=SimpleNamespace(read=lambda rid,binding:dict(profile=timing_profile(rid,binding)))
        self.live=SimpleNamespace(bind_instance=lambda b:None,closed=False,events=[],cleanup_confirmed=False,evidence=None,error=None)
        self.live.context=None
        def start(context):self.live.context=deepcopy(context)
        self.live.start=start
        self.live.snapshot=lambda:dict(connection_state='CONNECTED' if self.live.context else 'DISCONNECTED',live_heartbeat=bool(self.live.context),
            telemetry_age_ms=42,telemetry_sequence=3,drive_ready=True,control_state='READY',lidar_state='OFF',recording=None,
            battery=dict(voltage_v=11.8,percent=None,source='measured',age_ms=20),cleanup_confirmed=False)
        self.live.command=lambda action,payload,**kw:self.trace.append((action,deepcopy(payload),deepcopy(kw)))
        self.live.close=lambda:None
        self.pool=PhysicalFleetAdapter(self.devices,ROOT,self.tmp.name,services_factory=lambda binding,archive:PhysicalFleetServices(
            fixtures.Diagnostics('pool',self.trace),fixtures.Readiness('pool',self.trace),fixtures.Controller('pool',self.trace),self.live))
        self.devices.physical_fleet=self.pool
        self.broker=SimpleNamespace(project_id='project-a')
        self.engine=dict(engine_connected=True,engine_session_id='engine',stage_epoch='stage',snapshot=dict(applied_revision='scene-a'))
        self.broker.supervisor_state=lambda:deepcopy(self.engine)
        self.fleet=RobotFleet(self.broker,Path(self.tmp.name)/'project',devices=self.devices,wall=lambda:100.)
        self.addCleanup(self.fleet.close);self.addCleanup(self.pool.close)
        self.owner='offline-owner';self.identity=self.row['id']

    def action(self,action,payload=None,**overrides):
        row=self.fleet.snapshot()['robots'][0]
        body=dict(action=action,request_id=uuid4().hex,robot_id=self.identity,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],payload=payload or {})
        body.update(overrides)
        return self.fleet.action(body,self.owner)

    def test_voltage_only_worker_battery_preserves_nullable_public_percent(self):
        original=self.live.snapshot
        def voltage_only():
            value=original();value['battery'].pop('percent');return value
        self.live.snapshot=voltage_only
        self.action('focus');value=self.action('connect')['robots'][0]
        self.assertIsNone(value['battery']['percent'])
        self.assertEqual(value['battery']['voltage_v'],11.8)
        self.assertEqual(value['battery']['source'],'measured')
        self.assertEqual(value['battery']['age_ms'],62)
        self.assertEqual(value['battery']['estimated_percent'],72.2)
        self.assertEqual(value['battery']['estimate_method'],'robotis_opencr_voltage_10_5_to_12_3_v1')
        self.assertFalse(value['battery']['capacity_measured'])

    def test_fleet_row_passes_link_detail_owner_state_and_storage_through_and_marks_ended_rows(self):
        original=self.live.snapshot
        storage=dict(free_bytes=100*1024*1024,reserve_bytes=512*1024*1024,state='LOW')
        def degraded():
            value=original();value.update(connection_state='DEGRADED',live_heartbeat=False,
                link_detail='no fresh heartbeat for 3000 ms (limit 2500 ms)',remote_stderr_tail=None,
                recording_failure_reason='SESSION_DISK_LOW',control_owner_state='EXITED_RECONNECT_REQUIRED',
                last_reported_lidar_state='STREAMING',lidar_state_source='robot',robot_storage=storage)
            return value
        self.live.snapshot=degraded
        self.action('focus');row=self.action('connect')['robots'][0]
        self.assertEqual(row['connection_state'],'DEGRADED')
        self.assertEqual(row['link_detail'],'no fresh heartbeat for 3000 ms (limit 2500 ms)')
        self.assertEqual(row['reason'],'no fresh heartbeat for 3000 ms (limit 2500 ms)')
        self.assertEqual(row['control_owner_state'],'EXITED_RECONNECT_REQUIRED')
        self.assertEqual(row['recording_failure_reason'],'SESSION_DISK_LOW')
        self.assertEqual((row['last_reported_lidar_state'],row['lidar_state_source']),('STREAMING','robot'))
        self.assertEqual(row['robot_storage'],storage);self.assertIsNone(row['remote_stderr_tail'])
        self.live.closed=True
        row=self.fleet.snapshot()['robots'][0]
        self.assertEqual(row['connection_state'],'DISCONNECTED')
        self.assertIsNone(row['control_owner_state']);self.assertEqual(row['lidar_state_source'],'pc_after_exit')
        self.assertEqual(row['last_reported_lidar_state'],'STREAMING')

    def test_saved_display_changes_apply_to_existing_session_without_transport_or_age_reset(self):
        from twinpulse_core.robot_battery import battery_display_config
        self.action('focus');row=self.action('connect')['robots'][0];trace=len(self.trace)
        # Pool fixture uses an in-memory registry snapshot; actual atomic
        # registry persistence/CAS is covered in test_robot_registry_binding.
        self.row['battery_display']=battery_display_config()
        battery=self.fleet.snapshot()['robots'][0]['battery']
        self.assertIsNone(battery['estimated_percent']);self.assertEqual(battery['age_ms'],row['battery']['age_ms'])
        self.assertEqual(battery['voltage_v'],11.8);self.assertEqual(len(self.trace),trace)
        custom=battery_display_config('custom');custom['points']=[dict(voltage_v=10,percent=0),dict(voltage_v=12,percent=100)]
        self.row['battery_display']=custom
        battery=self.fleet.snapshot()['robots'][0]['battery']
        self.assertEqual(battery['estimated_percent'],90);self.assertEqual(battery['estimate_method'],'custom_voltage_table_v1')
        self.assertEqual(battery['low_voltage_guard_v'],11.1);self.assertEqual(len(self.trace),trace)

    def test_physical_payload_complete_and_age_not_replaced_with_sim_private_timestamp(self):
        self.action('focus');self.action('connect')
        value=self.action('drive',dict(direction='right',sequence=2,expires_at_ms=100250))
        self.assertEqual(self.trace[-1][0],'drive');self.assertEqual(self.trace[-1][1]['direction'],'right')
        self.assertEqual(self.trace[-1][1]['expires_at_ms'],100250)
        self.assertEqual(self.trace[-1][2]['motion_epoch'],value['robots'][0]['motion_epoch'])
        self.assertEqual(value['robots'][0]['telemetry_age_ms'],42)
        self.assertEqual(value['robots'][0]['battery']['age_ms'],62)
        self.assertIsNotNone(value['robots'][0]['operation_id'])

    def test_finite_chat_extent_and_stale_epoch_cannot_be_dropped(self):
        self.action('focus');self.action('connect')
        self.action('command',dict(text='turn right 90 degrees'),robot_id=None,connection_epoch=None,motion_epoch=None)
        self.assertEqual(self.trace[-1][0],'task');self.assertAlmostEqual(self.trace[-1][1]['amount'],1.5707963267948966)
        old=self.fleet.snapshot()['robots'][0]['motion_epoch']
        self.action('stop')
        with self.assertRaises(BrokerError):self.action('drive',dict(direction='forward',sequence=10,expires_at_ms=100250),motion_epoch=old)

    def test_late_chat_and_prepare_cannot_rebase_to_post_stop_motion_epoch(self):
        self.action('focus');old=self.action('connect')['robots'][0]
        self.action('stop');before=len(self.trace)
        for action,payload in [('command',dict(text='turn right 90 degrees')),('prepare',dict(confirmed=True)),('lidar',dict(enabled=True))]:
            with self.subTest(action=action),self.assertRaises(BrokerError):
                self.action(action,payload,connection_epoch=old['connection_epoch'],motion_epoch=old['motion_epoch'])
        self.assertEqual(len(self.trace),before)

    def test_chat_null_epochs_bind_before_slow_physical_refresh_not_after_stop(self):
        self.action('focus');self.action('connect')
        refresh=self.fleet._physical_values
        def delayed_refresh(**kwargs):
            self.pool.stop(self.identity,self.owner)
            return refresh(**kwargs)
        with patch.object(self.fleet,'_physical_values',side_effect=delayed_refresh):
            with self.assertRaises(BrokerError):
                self.action('command',dict(text='turn right 90 degrees'),robot_id=None,connection_epoch=None,motion_epoch=None)
        self.assertEqual(self.trace[-1][0],'stop')

    def test_other_project_does_not_gain_movement_from_workspace_session(self):
        self.action('focus');self.action('connect');self.broker.project_id='another'
        with self.assertRaises(BrokerError):self.action('drive',dict(direction='forward',sequence=1,expires_at_ms=100250))
        self.action('stop') # Owned stop still allowed.

    def test_estimated_marker_is_revision_bound_visual_only_and_restores_no_authority(self):
        value=self.action('set_twin_pose',dict(position_m=[1.,2.,.3]))
        row=value['robots'][0]
        self.assertFalse(self.trace);self.assertIsNone(row['pose']);self.assertIsNone(row['connection_epoch'])
        self.assertFalse(row['display_pose']['aligned'])
        report=dict(engine_session_id='engine',stage_epoch='stage',report=dict(applied_revision='scene-a',robots=[]))
        desired=self.fleet.engine_exchange('engine','stage',report)['fleet']['robots']
        self.assertEqual(len(desired),1);self.assertTrue(desired[0]['visual_only'])
        self.assertIsNone(desired[0]['intent']);self.assertIsNone(desired[0]['task']);self.assertFalse(desired[0]['lidar'])
        self.engine['snapshot']['applied_revision']='scene-b';report['report']['applied_revision']='scene-b'
        self.assertEqual(self.fleet.engine_exchange('engine','stage',report)['fleet']['robots'],[])

    def test_release_manual_keeps_independent_finite_task_and_sensor_session(self):
        self.action('focus');self.action('connect')
        self.action('command',dict(text='turn right 90 degrees'),robot_id=None,connection_epoch=None,motion_epoch=None)
        before=len(self.trace);epoch=self.pool._cached(self.identity).motion_epoch
        self.pool.release_manual(self.identity,self.owner)
        self.assertEqual(len(self.trace),before);self.assertEqual(self.pool._cached(self.identity).motion_epoch,epoch)
        self.action('drive',dict(direction='right',sequence=1,expires_at_ms=100250))
        self.pool.release_manual(self.identity,self.owner)
        self.assertEqual(self.trace[-1][0],'stop')


if __name__=='__main__':unittest.main()
