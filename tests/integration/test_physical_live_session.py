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
from tests.integration import test_physical_fleet_adapter as fixtures


class PhysicalLiveSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=10.;self.wall=100.
        self.session=PhysicalLiveSession(ROOT,self.tmp.name,identity=Path('unused'),known_hosts=Path('unused'),
            process_factory=lambda *a,**k:self.fail('No SSH in supplementary tests'),clock=lambda:self.now,wall=lambda:self.wall)
        self.context=dict(operation_id=uuid4().hex,robot_id=uuid4().hex,project_id='project-a',connection_epoch=uuid4().hex,motion_epoch=uuid4().hex)
        self.session.context=dict(self.context,worker_sha256='a'*64)

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
        self.assertEqual(packet['payload']['source_age_ms'],50)
        for key in ('robot_id','operation_id','project_id','connection_epoch','motion_epoch'):self.assertEqual(packet[key],self.context[key])
        self.assertEqual(packet['request_id'],request)
        with self.assertRaises(BrokerError):self.session.command('drive',dict(direction='forward',sequence=8,expires_at_ms=100000),
            motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.assertTrue(self.session.writes.empty())

    def test_stop_discards_queued_drives_even_stale_heartbeat_and_watch_cannot_drive(self):
        self.heartbeat()
        for i in range(4):self.session.command('drive',dict(direction='forward',sequence=i+1,expires_at_ms=100250),motion_epoch=self.context['motion_epoch'],request_id=uuid4().hex)
        self.now+=10
        self.session.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
        self.assertEqual(self.session.writes.qsize(),1)
        self.assertEqual(self.session.writes.get_nowait()['action'],'stop')
        with self.assertRaises(BrokerError):self.session.command('task',dict(direction='left',amount=1),motion_epoch=uuid4().hex,request_id=uuid4().hex)

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
                    self.event('heartbeat',dict(challenge='motor-nonce',watch_challenge='presence-nonce',motion_generation=1,
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
                try:session.command('drive',dict(direction='forward',sequence=sequence,expires_at_ms=time.time()*1000+250),
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
            self.assertTrue(all(c['payload']['challenge']=='presence-nonce' for c in watches))
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
        self.devices=SimpleNamespace(registry_service=SimpleNamespace(registry=SimpleNamespace(snapshot=lambda:dict(robots=[deepcopy(self.row)]))),
            lock=RLock(),closed=False,contexts=[],diagnostics=fixtures.Diagnostics('legacy',self.trace),readiness=fixtures.Readiness('legacy',self.trace),controller=fixtures.Controller('legacy',self.trace))
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
