# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""OFFLINE: saved serial bytes and synthetic injected owners; zero hardware I/O."""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict,replace
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import queue
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/tests'))
from native_stream import NativeDecoder,NativeStream
from physical_profile import checked_profile,profile_objects,profile_sha256
from fleet_control import RobotControl,NativeOutputGuard
from fleet_worker import checked_context,checked_command,SegmentedWriter,InputLines,FleetWorker,export_sources
from test_manual_motion_guard import fixture
from twinpulse_core.manual_motion_guard import ProgressThresholds,evaluate_manual_motion,WheelBodyProgressMonitor,ProgressObservation

SHA='a'*64

def profile():
    frame,geometry,sampling,stop,intent=fixture()
    threshold=ProgressThresholds(.2,.1,.001,.00001,.001,.001,.2,.2,1.,'measured',SHA)
    result=dict(schema='physical-manual-profile-1.0',robot_id='b'*32,binding_sha256=SHA,
        geometry=asdict(geometry),sampling=asdict(sampling),stop_model=asdict(stop),
        timing=dict(maximum_pipeline_age_s=.01,measurement_sha256=SHA,provenance='measured'),
        progress=dict(asdict(threshold),wheel_metres_per_tick=.00005,wheel_separation_m=.16,
                      body_progress_policy='explicitly_unverified_supervised'))
    for name in ('geometry','sampling','stop_model','progress'):result[name].pop('provenance')
    return json.loads(json.dumps(result))

def context():
    return dict(schema='physical-live-start-1.0',operation_id='o'*32,robot_id='b'*32,project_id='default',
        connection_epoch='c'*32,binding_sha256=SHA,worker_sha256=SHA)

def command(action='stop',sequence=1,payload=None):
    return dict(schema='physical-live-command-1.0',**{k:context()[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
        motion_epoch='m'*32,request_id='r'*32,sequence=sequence,action=action,payload=payload or {})

def packet(*,count=2,first=20.,last=22.,ring=False):
    a,b=int(first*64)*2+1,int(last*64)*2+1
    ct=int(ring);payload=b''.join(bytes((200<<2&255,((200>>6)&3)|((1000%64)<<2),1000//64)) for _ in range(count))
    checksum=0x55aa^(ct|count<<8)^a^b
    for i in range(0,len(payload),3):checksum^=payload[i]^int.from_bytes(payload[i+1:i+3],'little')
    return b'\xaa\x55'+struct.pack('<BBHHH',ct,count,a,b,checksum)+payload


class DecoderTests(unittest.TestCase):
    def test_saved_full_recordings_match_corrected_vendor_every_node(self):
        saved=ROOT/'outputs/robot-obstacle-prior-20261017'
        expected=ROOT/'outputs/robot-fleet-20261017/decoder-results-03'
        total=0
        for name,file in [('sensor-only-raw-18','raw.bin')]+[(f'moving-native-23{x}','native-lidar.raw') for x in ('b','f','h')]:
            data=(saved/name/file).read_bytes();decoder=NativeDecoder();packets=[]
            for start in range(0,len(data),137):packets+=decoder.feed(data[start:start+137],1.+start/100000)
            nodes=[n for p in packets for n in p['nodes']]
            wanted=[json.loads(line) for line in (expected/(name+'-nodes.ndjson')).read_text().splitlines()]
            self.assertEqual(len(nodes),len(wanted),name)
            for i,(actual,reference) in enumerate(zip(nodes,wanted)):
                for key,value in reference.items():
                    self.assertEqual(float(format(actual[key],'.6g')) if key in {'angle_deg','distance_m'} else actual[key],value,(name,i,key))
            total+=len(nodes)
        self.assertGreater(total,100000)

    def test_overlapping_header_chunk_timing_and_truncated_tail(self):
        raw=b'\xaa'+packet();d=NativeDecoder()
        self.assertEqual(d.feed(raw[:8],1.),[])
        rows=d.feed(raw[8:]+b'\xaa\x55\x01',1.1)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['offset'],1)
        self.assertEqual(rows[0]['receipt_start_s'],1.);self.assertEqual(rows[0]['receipt_end_s'],1.1)
        self.assertEqual(bytes(d.buffer),b'\xaa\x55\x01')

    def test_invalid_checksum_never_free_and_oversized_counts_resync(self):
        bad=bytearray(packet());bad[-1]^=1
        packets=NativeDecoder().feed(bytes(bad)+packet(),1.)
        self.assertFalse(packets[0]['checksum_valid'])
        self.assertTrue(all(n['distance_m']==0 and n['quality']==10 for n in packets[0]['nodes']))
        self.assertTrue(packets[1]['checksum_valid'])
        self.assertEqual(len(NativeDecoder().feed(b'\xaa\x55\x00\xff'+b'\x01'*6+packet(),1.)),1)

    def test_independent_stream_start_stop_bounded_segments_raw_receipts(self):
        events=[]
        class Channel:
            cleanup=staticmethod(nullcontext)
            def __init__(self):self.calls=[];self.n=0
            def configure(self):self.calls.append('configure')
            def write(self,v):self.calls.append(v);return len(v)
            def read(self,_):
                self.n+=1
                if self.n<=4:return packet(count=40,ring=True)+packet(count=40)
                stream.stop();return b''
            def drain(self,_):return 0
            def restore(self):return True
            def close(self):self.calls.append('close')
        channel=Channel()
        with tempfile.TemporaryDirectory() as tmp:
            stream=NativeStream(tmp,lambda kind,data:events.append((kind,data)),channel_factory=lambda:channel,
                                segment_bytes=1024,maximum_bytes=4096)
            self.assertEqual(channel.calls,[])
            stream.start();stream.thread.join(2)
            self.assertEqual(stream.snapshot()['lidar_state'],'OFF')
            result=stream.snapshot()['manifest'];self.assertTrue(result['complete'])
            self.assertEqual(result['bytes_received'],1040);self.assertEqual(len(result['segments']),2)
            raws=[v for kind,v in events if kind=='raw'];self.assertEqual(len(raws),4)
            scans=[v for kind,v in events if kind=='scan'];self.assertTrue(scans)
            self.assertEqual(scans[0]['timing']['basis'],'serial_receipt_unqualified')
            self.assertIsNone(scans[0]['timing']['acquisition_earliest_s'])


class ProfileAndGuardTests(unittest.TestCase):
    def test_supervised_profile_preserves_null_unused_body_thresholds_and_existing_values(self):
        body=('minimum_body_translation_m','minimum_body_rotation_rad','maximum_body_speed_m_s','maximum_body_rotation_rad_s')
        original=profile();old_hash=profile_sha256(original)
        self.assertEqual(checked_profile(original),original)
        self.assertEqual(profile_sha256(checked_profile(original)),old_hash)
        value=deepcopy(original)
        for key in body:value['progress'][key]=None
        accepted=checked_profile(value)
        self.assertEqual(accepted,value);self.assertEqual(accepted['schema'],'physical-manual-profile-1.0')
        thresholds=profile_objects(accepted)[-1]
        self.assertTrue(all(getattr(thresholds,key) is None for key in body))
        WheelBodyProgressMonitor(thresholds,require_independent_body=False)
        for key in body:
            for bad_value in (0,-1,float('nan'),float('inf'),True):
                bad=deepcopy(value);bad['progress'][key]=bad_value
                with self.assertRaisesRegex(ValueError,'PROFILE_MEASURED_PROGRESS_REQUIRED'):checked_profile(bad)
            bad=deepcopy(original);bad['progress']['body_progress_policy']='independent_required';bad['progress'][key]=None
            with self.assertRaisesRegex(ValueError,'PROFILE_MEASURED_PROGRESS_REQUIRED'):checked_profile(bad)
        for key in ('minimum_command_m_s','minimum_wheel_progress_m','maximum_wheel_speed_m_s','wheel_metres_per_tick','wheel_separation_m','measurement_sha256'):
            bad=deepcopy(value);bad['progress'][key]=None
            with self.assertRaisesRegex(ValueError,'PROFILE_MEASURED_PROGRESS_REQUIRED'):checked_profile(bad)

    def test_profile_exact_bounds_and_binding_no_defaults(self):
        value=profile();self.assertEqual(checked_profile(value),value);profile_objects(value)
        for path,new in [('maximum_linear_speed_m_s',.051),('maximum_angular_speed_rad_s',.301),('maximum_input_age_s',.351)]:
            bad=deepcopy(value);bad['stop_model'][path]=new
            with self.assertRaises(ValueError):checked_profile(bad)
        with self.assertRaises(ValueError):checked_profile(value,robot_id='c'*32)
        bad=deepcopy(value);bad['timing']['provenance']='estimated'
        with self.assertRaises(ValueError):checked_profile(bad)
        self.assertNotIn('provenance',value['geometry'])

    def test_measured_interval_requires_bound_evidence_not_relabelled_receipt(self):
        f,g,s,p,i=fixture()
        interval=replace(f,timestamp_basis='conservative_measured_interval')
        self.assertFalse(evaluate_manual_motion(i,interval,g,s,p,1.)['model_clear'])
        interval=replace(interval,timing_evidence_sha256=SHA,maximum_pipeline_age_s=.01)
        self.assertTrue(evaluate_manual_motion(i,interval,g,s,p,1.)['model_clear'])
        self.assertFalse(evaluate_manual_motion(i,replace(interval,oldest_sample_s=.79),g,s,p,1.)['model_clear'])

    def test_explicit_wheel_only_policy_keeps_body_unverified(self):
        thresholds=profile_objects(profile())[-1]
        monitor=WheelBodyProgressMonitor(thresholds,require_independent_body=False)
        for index in range(4):
            t=1.+index*.08
            result=monitor.observe(ProgressObservation(t,'one',(index*.001,index*.001),0.,None,0.,0.,'wheel_encoder_only',None,None),
                                   (.03,.03),progress_kind='translation',now=t)
        self.assertEqual(result['body_progress'],'UNVERIFIED');self.assertFalse(result['requires_stop'])
        self.assertEqual(result['wheel_progress'],'MOVING')

    def test_cross_axis_noise_needs_measured_uncertainty_and_extra_coverage(self):
        f,g,s,p,i=fixture()
        small=replace(i,measured_angular_rad_s=.001)
        result=evaluate_manual_motion(small,f,g,s,p,1.)
        self.assertTrue(result['model_clear']);self.assertTrue(result['measured_cross_axis_envelope'])
        self.assertFalse(evaluate_manual_motion(replace(i,measured_angular_rad_s=.02),f,g,s,p,1.)['model_clear'])
        rear=replace(f,beams=tuple(replace(b,distance_m=0.) if 130<b.angle_deg<230 else b for b in f.beams))
        self.assertFalse(evaluate_manual_motion(small,rear,g,s,p,1.)['model_clear'])

    def test_runtime_native_guard_consumes_original_frame_and_blocks_stale(self):
        f,g,s,p,i=fixture();p=profile()
        frame={'complete':True,'interval_fallback':False,'raw_sha256':SHA,'nodes_sha256':SHA,
            'beams':[dict(asdict(b),valid_packet=True) for b in f.beams],
            'timing':dict(basis='conservative_measured_interval',acquisition_earliest_s=.95,
                acquisition_latest_s=.99,evidence_sha256=SHA,uncertainty_s=.01)}
        native=SimpleNamespace(latest_frame=lambda:deepcopy(frame))
        link=SimpleNamespace(rows=[dict(t=.95,source_age_s=0.,encoders=[0,0]),dict(t=.99,source_age_s=0.,encoders=[0,0])])
        guard=NativeOutputGuard(p,native,link,clock=lambda:1.)
        guard(.03,0.,.9);self.assertTrue(guard.last_result['model_clear'])
        frame['timing']['acquisition_earliest_s']=.79
        with self.assertRaisesRegex(ValueError,'BEAM_TIMING_MISSING_OR_STALE'):guard(.03,0.,.9)
        frame['timing']['acquisition_earliest_s']=.95;frame['beams'][0]['distance_m']=.2
        with self.assertRaisesRegex(ValueError,'OBSTACLE'):guard(.03,0.,.9)

    def test_ros_actual_publisher_hook_blocks_before_nonzero_output(self):
        import teleop_ros
        output=[];link=teleop_ros.RosLink.__new__(teleop_ros.RosLink)
        link.fresh=lambda:None;link.sensor=SimpleNamespace(torque=True);link.reason='active';link.manual_speed_profile=True
        link.node=SimpleNamespace(get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=10**9)))
        link.Twist=lambda:SimpleNamespace(header=SimpleNamespace(frame_id='',stamp=SimpleNamespace(sec=0,nanosec=0)),
            twist=SimpleNamespace(linear=SimpleNamespace(x=0),angular=SimpleNamespace(z=0)))
        link.pub=SimpleNamespace(publish=output.append)
        def reject(*_):raise ValueError('NATIVE_OBSTACLE_FIXTURE')
        link.native_output_guard=reject
        with patch.object(teleop_ros.time,'monotonic',lambda:1.):
            with self.assertRaisesRegex(ValueError,'NATIVE_OBSTACLE'):link.publish(.05,0.,.01)
            self.assertEqual(output,[])
            checked=[];link.native_output_guard=lambda *args:checked.append(args)
            link.publish(.05,0.,.01)
        self.assertEqual(len(output),1);self.assertEqual(checked,[(.05,0.,.99)])


class ProtocolTests(unittest.TestCase):
    def test_binding_replay_and_stop_after_dropped_sequence(self):
        c=context();self.assertEqual(checked_context(c),c)
        self.assertEqual(checked_command(command(sequence=20),c,1)['sequence'],20)
        self.assertEqual(checked_command(command(sequence=2),c,20)['action'],'stop')
        with self.assertRaises(ValueError):checked_command(command('drive',2),c,20)
        bad=command();bad['project_id']='other'
        with self.assertRaisesRegex(ValueError,'IDENTITY'):checked_command(bad,c,0)

    def test_watch_cannot_renew_manual_expiry(self):
        now=[1.];native=SimpleNamespace()
        owner=RobotControl(context(),'.',lambda *_:None,native,clock=lambda:now[0])
        nonce=owner.gate.challenge()
        owner.gate.accept(dict(sequence=1,action='forward',challenge=nonce,age_ms=0))
        old=(owner.gate.deadline,owner.gate.source_created,owner.gate.hold_end)
        now[0]=1.1;nonce=owner.gate.challenge()
        owner._command(command('watch',2,dict(challenge=nonce,source_age_ms=0,motion_generation=0)))
        self.assertEqual(old,(owner.gate.deadline,owner.gate.source_created,owner.gate.hold_end))
        now[0]=1.351
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):owner.gate.check()

    def test_prearm_probe_not_reused_as_wheel_progress_window(self):
        now=[1.];resets=[]
        owner=RobotControl(context(),'.',lambda *_:None,SimpleNamespace(snapshot=lambda:{'lidar_state':'STREAMING'}),clock=lambda:now[0])
        owner.profile=profile();owner._qualification=lambda:True
        class Guard:
            def __call__(self,*_):resets.append('prearm_probe')
            def reset(self):resets.append('reset')
        class Link:
            enabled=False
            def enable(self):now[0]+=.11;self.enabled=True
        owner.guard=Guard();owner.link=Link()
        nonce=owner.gate.challenge()
        owner._command(command('drive',1,dict(direction='forward',challenge=nonce,source_age_ms=0,motion_generation=0)))
        self.assertEqual(resets,['prearm_probe','reset'])
        self.assertEqual(owner.snapshot()['control_state'],'ARMED_AWAITING_FRESH_INPUT')
        self.assertIsNone(owner.direction);self.assertIsNone(owner.gate.source_created)

    def test_lower_measured_caps_bound_prearm_and_published_command_in_all_directions(self):
        for direction,expected in [('forward',(.03,0.)),('backward',(-.03,0.)),('left',(0.,.2)),('right',(0.,-.2))]:
            with self.subTest(direction=direction):
                now=[1.];probes=[];published=[];events=[]
                owner=RobotControl(context(),'.',lambda *a:events.append(a),
                    SimpleNamespace(snapshot=lambda:{'lidar_state':'STREAMING'}),clock=lambda:now[0])
                owner.profile=profile();owner.profile['stop_model'].update(maximum_linear_speed_m_s=.03,maximum_angular_speed_rad_s=.2)
                checked_profile(owner.profile);owner._qualification=lambda:True;owner._pose=lambda:None
                class Guard:
                    last_result={'model_clear':True};progress={'body_progress':'UNVERIFIED'}
                    def __call__(self,v,w,_):probes.append((v,w))
                    def reset(self):pass
                class Link:
                    enabled=False;sensor=SimpleNamespace(torque=True,battery=12.);sensor_t=1.
                    def enable(self):self.enabled=True
                    def spin(self,_):self.sensor_t=now[0]
                    def fresh(self):pass
                    def publish(self,v,w,age,**_):published.append((v,w));return {'allowed':True}
                owner.guard=Guard();owner.link=Link()
                for sequence in (1,2):
                    now[0]+=.01;nonce=owner.gate.challenge()
                    owner._command(command('drive',sequence,dict(direction=direction,challenge=nonce,source_age_ms=0,motion_generation=owner.gate.generation)))
                owner._tick()
                self.assertEqual(probes,[expected]);self.assertEqual(published,[expected])
                ack=next(v for _,v in events if v.get('status')=='PUBLISHED')
                self.assertEqual((ack['linear_m_s'],ack['angular_rad_s']),expected)

    def test_lower_cap_task_deadline_uses_actual_speed_and_legacy_trial_never_exceeds_profile(self):
        now=[1.]
        owner=RobotControl(context(),'.',lambda *_:None,
            SimpleNamespace(snapshot=lambda:{'lidar_state':'STREAMING'}),clock=lambda:now[0])
        owner.profile=profile();owner.profile['stop_model']['maximum_linear_speed_m_s']=.03
        owner.link=SimpleNamespace(enabled=True);owner._qualification=lambda:True
        owner._pose=lambda:dict(x=0.,y=0.,yaw=0.,frame_id='odom',sample_s=1.)
        owner._command(command('task',1,dict(direction='forward',amount=.3,challenge=owner.gate.challenge(),source_age_ms=0,motion_generation=0)))
        self.assertAlmostEqual(owner.task['deadline'],13.)
        owner._qualification=lambda:False
        with patch('teleop_worker.qualify') as trial:
            with self.assertRaisesRegex(ValueError,'LEGACY_QUALIFICATION_REQUIRES_0_05_PROFILE_CAP'):
                owner._qualify(command('qualify',2,{'confirmed':True}))
            trial.assert_not_called()

    def test_independent_body_policy_is_explicitly_unimplemented_before_arming(self):
        owner=RobotControl(context(),'.',lambda *_:None,SimpleNamespace(snapshot=lambda:{'lidar_state':'STREAMING'}))
        owner.profile=profile();owner.profile['progress']['body_progress_policy']='independent_required'
        owner.link=SimpleNamespace(enabled=False);owner._qualification=lambda:True
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_BODY_PROGRESS_SOURCE_NOT_IMPLEMENTED'):
            owner._movement_ready()

    def test_manual_replaces_task_without_inheriting_watch_renewal(self):
        now=[1.]
        owner=RobotControl(context(),'.',lambda *_:None,
            SimpleNamespace(snapshot=lambda:{'lidar_state':'STREAMING'}),clock=lambda:now[0])
        owner.profile=profile();owner._qualification=lambda:True
        owner.link=SimpleNamespace(enabled=True)
        owner.direction='forward';owner.task={'status':'RUNNING','deadline':100.}
        nonce=owner.gate.challenge()
        owner._command(command('drive',1,dict(direction='forward',challenge=nonce,
            source_age_ms=0,motion_generation=0)))
        self.assertIsNone(owner.task);self.assertIsNone(owner.snapshot()['task'])
        original=(owner.gate.deadline,owner.gate.source_created,owner.gate.hold_end)
        now[0]=1.1;nonce=owner.gate.challenge()
        owner._command(command('watch',2,dict(challenge=nonce,source_age_ms=0,motion_generation=0)))
        self.assertEqual(original,(owner.gate.deadline,owner.gate.source_created,owner.gate.hold_end))
        now[0]=1.351
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):owner.gate.check()

    def test_stop_clears_queued_drive_and_has_priority(self):
        owner=RobotControl(context(),'.',lambda *_:None,SimpleNamespace())
        owner.submit(command('drive',1));owner.submit(command('drive',2));owner.submit(command('stop',3))
        self.assertTrue(owner.stop_requested.is_set());self.assertEqual(owner.queue.qsize(),1)
        self.assertEqual(owner.queue.get()['action'],'stop')

    def test_input_nonfinite_and_truncated_lines_rejected(self):
        for content in (b'{"a":NaN}\n',b'{}'):
            lines=InputLines(io.BytesIO(content));self.assertTrue(lines.failed.wait(1));self.assertTrue(lines.messages.empty())

    def test_preparing_presence_does_not_queue_watch_or_create_motor_lease(self):
        class Control:
            def __init__(self,*_,**__):self.queued=[]
            def snapshot(self):return dict(control_state='PREPARING',battery={'voltage_v':None},blockers=[])
            def submit(self,c):self.queued.append(c)
        class Native:
            def __init__(self,*_):pass
            def latest_frame(self):return None
            def snapshot(self):return {'lidar_state':'OFF'}
        now=[1.];events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(context(),tmp,events.append,clock=lambda:now[0],control_factory=Control,native_factory=Native)
            worker.context.update(boot_id='boot',release_id=SHA)
            for i in range(40):
                now[0]=1.+i*.1
                heartbeat=worker.heartbeat()
                worker.command(command('watch',i+1,dict(challenge=heartbeat['watch_challenge'],source_age_ms=0,motion_generation=0)))
            self.assertEqual(worker.control.queued,[])
            worker.journal.close();worker.protocol.close()
            self.assertEqual(len(events),40)
            self.assertTrue(all(e['data']['scope']=='PREPARATION_PRESENCE_ONLY_NO_MOTION_LEASE' for e in events))
            self.assertNotIn('watch_challenge',(Path(tmp)/'events-000000.jsonl').read_text())

    def test_slow_qualification_cleanup_presence_does_not_overflow_control_or_erase_stop(self):
        class Native:
            def __init__(self,*_):pass
            def latest_frame(self):return None
            def snapshot(self):return {'lidar_state':'OFF'}
        now=[1.];events=[];entered=threading.Event();release=threading.Event()
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(context(),tmp,events.append,clock=lambda:now[0],native_factory=Native)
            worker.context.update(boot_id='boot',release_id=SHA)
            owner=worker.control;owner._update(control_state='QUALIFYING',watch_challenge='old-qualification-nonce')
            def halt():entered.set();release.wait(2)
            owner.link=SimpleNamespace(halt=halt,close=lambda:None)
            owner.lease=SimpleNamespace(fileno=lambda:1);owner.lease_context=nullcontext();owner.lease_context.__enter__()
            owner._read_board=lambda _:{};owner.stop_requested.set()
            cleanup=[]
            with patch('runtime.disarm_board'),patch('stationary.require_idle'):
                thread=threading.Thread(target=lambda:cleanup.append(owner._cleanup()),daemon=True);thread.start()
                try:
                    self.assertTrue(entered.wait(1))
                    for i in range(40):
                        now[0]=1.+i*.1
                        heartbeat=worker.heartbeat()
                        worker.command(command('watch',i+1,dict(challenge=heartbeat['watch_challenge'],source_age_ms=0,motion_generation=0)))
                    self.assertTrue(owner.queue.empty());self.assertTrue(owner.stop_requested.is_set())
                    self.assertFalse(owner.gate.active);self.assertIsNone(owner.gate.source_created)
                    self.assertFalse(owner.snapshot()['drive_ready'])
                    worker.cancel.set();heartbeat=worker.heartbeat()
                    with self.assertRaisesRegex(ValueError,'SESSION_CLOSING'):
                        worker.command(command('watch',41,dict(challenge=heartbeat['watch_challenge'],source_age_ms=0,motion_generation=0)))
                finally:
                    release.set();thread.join(2)
                    worker.journal.close();worker.protocol.close()
            self.assertTrue(cleanup[0]['cleanup_confirmed'])
            self.assertIsNone(owner.snapshot()['maintenance_phase'])
            watches=[e for e in events if e['kind']=='command']
            self.assertEqual(len(watches),40)
            self.assertTrue(all(e['data']['scope']=='CLEANUP_PRESENCE_ONLY_NO_MOTION_LEASE' for e in watches))

    def test_runtime_main_rejects_before_any_device_with_safe_reason_only(self):
        import subprocess
        import os
        value=context();value['worker_sha256']='not-a-hash'
        p=subprocess.run([sys.executable,'-B',str(ROOT/'packages/twinpulse_robot_safety/fleet_worker.py')],
            input=(json.dumps(value)+'\n').encode(),capture_output=True,timeout=4,
            env=dict(os.environ,PYTHONPATH=str(ROOT/'packages/twinpulse_core/src')))
        self.assertEqual(p.returncode,2);self.assertEqual(p.stdout,b'')
        self.assertIn(b'FLEET_WORKER_REJECTED:START_DIGEST',p.stderr)
        self.assertNotIn(str(ROOT).encode(),p.stderr)

    def test_segment_capacity_and_hash_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer=SegmentedWriter(tmp,segment_bytes=8,maximum_bytes=16)
            writer.write('abcdef\n');writer.write('ghijkl\n')
            with self.assertRaises(OSError):writer.write('more')
            writer.close();self.assertEqual(len(writer.segments),2)
            self.assertTrue(all(len(s['sha256'])==64 for s in writer.segments))

    def test_explicit_prepare_confirmation_before_any_hardware_call(self):
        owner=RobotControl(context(),'.',lambda *_:None,SimpleNamespace())
        with patch.object(owner,'_prepare') as prepare:
            with self.assertRaisesRegex(ValueError,'CONFIRMATION'):owner._command(command('prepare'))
            prepare.assert_not_called()
            owner._command(command('prepare',payload={'confirmed':True}));prepare.assert_called_once()

    def test_repeated_board_reads_parse_only_new_bytes_but_preserve_raw_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=RobotControl(context(),tmp,lambda *_:None,SimpleNamespace())
            owner.release=Path('unused');owner.lease=SimpleNamespace(fileno=lambda:1)
            calls=[]
            def read(_release,path,_fd):
                calls.append(len(calls)+1)
                with path.open('ab') as stream:stream.write(('READ '+str(calls[-1])+'\n').encode())
            def parse(raw):
                self.assertEqual(len(raw.splitlines()),1)
                return {'current':raw.strip()}
            with patch('runtime.read_board',read),patch.dict(sys.modules,{'robot_health':SimpleNamespace(parse_board_snapshot=parse)}):
                self.assertEqual(owner._read_board('prepare-before')['current'],'READ 1')
                self.assertEqual(owner._read_board('prepare-before')['current'],'READ 2')
            self.assertEqual((Path(tmp)/'prepare-before.log').read_bytes(),b'READ 1\nREAD 2\n')

    def test_fixed_source_export_keeps_exact_bytes_and_ignores_unlisted_files(self):
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            raw=b'original helper output\n'+bytes(range(256))*100
            (Path(tmp)/'base.log').write_bytes(raw)
            (Path(tmp)/'unlisted.txt').write_bytes(b'never exported')
            manifest=export_sources(tmp,lambda kind,data:events.append((kind,data)))
            self.assertTrue(manifest['complete'])
            chunks=[data for kind,data in events if data['kind']=='chunk']
            self.assertEqual(b''.join(base64.b64decode(row['base64']) for row in chunks),raw)
            self.assertEqual([row['offset'] for row in chunks],[0,16384])
            member=next(row for row in manifest['members'] if row['member']=='base.log')
            self.assertEqual(member['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertNotIn('unlisted.txt',repr(events))

    def test_source_truncation_and_active_owner_never_claim_whole_file_sha(self):
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'base.log').write_bytes(b'0123456789')
            manifest=export_sources(tmp,lambda kind,data:events.append(data),member_limit=4,total_limit=4)
            self.assertFalse(manifest['complete'])
            member=next(row for row in manifest['members'] if row['member']=='base.log')
            self.assertEqual(member['status'],'TRUNCATED_BUDGET');self.assertIsNone(member['source_sha256'])
            chunk=next(row for row in events if row['kind']=='chunk')
            self.assertEqual(chunk['offset'],6);self.assertEqual(base64.b64decode(chunk['base64']),b'6789')
            active=export_sources(tmp,lambda *_:None,owners_reaped=False)
            member=next(row for row in active['members'] if row['member']=='base.log')
            self.assertFalse(active['complete']);self.assertEqual(member['status'],'SOURCE_ACTIVE_OR_CHANGED')

    def test_final_cleanup_failure_cannot_be_promoted_by_thread_exit(self):
        class Control:
            def __init__(self,*_,**__):self.stop_requested=threading.Event()
            def start(self):pass
            def snapshot(self):return {'control_state':'UNPREPARED'}
            def close(self):return dict(control_state='CLOSED',worker_reaped=True,cleanup_confirmed=False)
        class Native:
            def __init__(self,*_):pass
            def stop(self):pass
            def close(self):return {'lidar_state':'OFF'}
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(context(),tmp,events.append,control_factory=Control,native_factory=Native)
            worker._idle_board=lambda:None
            incoming=InputLines(io.BytesIO(b''));incoming.failed.wait(1)
            self.assertEqual(worker.run(incoming),2)
            self.assertFalse(events[-1]['data']['confirmed'])
            self.assertFalse(json.loads((Path(tmp)/'receipt.json').read_text())['complete'])

    def test_final_disk_flush_failure_reaches_pc_terminal_ack(self):
        class Control:
            def __init__(self,*_,**__):self.stop_requested=threading.Event()
            def start(self):pass
            def close(self):return dict(control_state='CLOSED',worker_reaped=True,cleanup_confirmed=True)
        class Native:
            def __init__(self,*_):pass
            def stop(self):pass
            def close(self):return {'lidar_state':'OFF'}
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(context(),tmp,events.append,control_factory=Control,native_factory=Native)
            worker._idle_board=lambda:None
            original=worker.journal.close
            worker.journal.close=lambda **kwargs:dict(original(**kwargs),error='FINAL_FLUSH_FIXTURE')
            incoming=InputLines(io.BytesIO(b''));incoming.failed.wait(1)
            worker.run(incoming)
            self.assertEqual(events[-1]['data']['subsystem'],'session')
            self.assertTrue(events[-1]['data']['confirmed'])
            self.assertFalse(events[-1]['data']['recording_complete'])
            self.assertFalse(json.loads((Path(tmp)/'receipt.json').read_text())['complete'])

    def test_finite_360_task_unwraps_yaw_and_never_resumes_after_pause(self):
        now=[1.];events=[]
        native=SimpleNamespace(snapshot=lambda:{'lidar_state':'STREAMING'})
        owner=RobotControl(context(),'.',lambda *a:events.append(a),native,clock=lambda:now[0])
        owner.profile=profile();owner._qualification=lambda:True
        pose={'x':0.,'y':0.,'yaw':0.,'frame_id':'odom','sample_s':1.}
        class Link:
            enabled=True;sensor=SimpleNamespace(torque=True,battery=12.);sensor_t=1.
            def spin(self,_):self.sensor_t=now[0]
            def fresh(self):pass
            def publish(self,*_,**__):return {'allowed':True}
            def release(self):self.enabled=False;self.sensor.torque=False
        owner.link=Link();owner._pose=lambda:deepcopy(pose)
        owner.guard=SimpleNamespace(last_result={'model_clear':True},progress={'body_progress':'UNVERIFIED'},reset=lambda:None)
        nonce=owner.gate.challenge()
        owner._command(command('task',1,dict(direction='left',amount=math.tau,scan=True,
            challenge=nonce,source_age_ms=0,motion_generation=0)))
        self.assertEqual(owner.task['amount'],math.tau)
        for i in range(1,219):
            now[0]=1.+i*.1;pose['sample_s']=now[0];pose['yaw']=math.remainder(i*.029,math.tau)
            nonce=owner.gate.challenge()
            owner._command(command('watch',i+1,dict(challenge=nonce,source_age_ms=0,motion_generation=0)))
            owner._tick()
            if owner.task is None:break
        self.assertIsNone(owner.task);self.assertEqual(owner.snapshot()['reason'],'TASK_WHEEL_ODOM_TARGET_REACHED')
        receipt=owner.snapshot()['command']
        self.assertEqual(receipt['state'],'COMPLETED');self.assertEqual(receipt['request_id'],'r'*32)
        self.assertTrue(receipt['stop_readback_confirmed']);self.assertEqual(receipt['result_basis'],'wheel_odom_not_independent_body')
        self.assertFalse(owner.link.enabled)
        self.assertTrue(any(data.get('status')=='PUBLISHED' for _,data in events))
        nonce=owner.gate.challenge();owner._command(command('watch',300,dict(challenge=nonce,source_age_ms=0,motion_generation=owner.gate.generation)))
        self.assertIsNone(owner.direction);self.assertIsNone(owner.task)

    def test_finite_completion_requires_actual_release_readback(self):
        owner=RobotControl(context(),'.',lambda *_:None,SimpleNamespace(),clock=lambda:1.)
        owner.state['command']=dict(request_id='original-request',kind='finite',state='RUNNING',text='turn right 90 degrees')
        def failed_release():raise ValueError('RELEASE_READBACK_FIXTURE')
        owner.link=SimpleNamespace(enabled=True,sensor=SimpleNamespace(torque=True),release=failed_release)
        with self.assertRaisesRegex(ValueError,'RELEASE_READBACK'):owner._pause('TASK_WHEEL_ODOM_TARGET_REACHED')
        receipt=owner.snapshot()['command']
        self.assertEqual(receipt['state'],'FAILED');self.assertFalse(receipt['stop_readback_confirmed'])
        self.assertEqual(receipt['request_id'],'original-request');self.assertEqual(receipt['reason'],'STOP_READBACK_UNCONFIRMED')

    def test_guard_build_failure_before_device_lease_disarm_or_driver_start(self):
        import runtime
        import guard_runtime
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);(home/'current').mkdir()
            (home/'current/profile.json').write_text(json.dumps(dict(manual_control_policy='explicit_session_and_same_boot_release_stop_receipt')))
            value=dict(context(),release_id='a'*64)
            owner=RobotControl(value,tmp,lambda *_:None,SimpleNamespace())
            with patch.object(runtime,'HOME',home),patch.object(runtime,'verify_release',return_value={'source_id':'a'*64}),\
                 patch.object(guard_runtime,'ensure',side_effect=ValueError('BUILD_FAILED_FIXTURE')),\
                 patch.object(runtime,'ownership') as lease,patch.object(runtime,'disarm_board') as off,patch.object(owner,'_read_board') as read,\
                 patch('fleet_control.subprocess.Popen') as start:
                with self.assertRaisesRegex(ValueError,'BUILD_FAILED_FIXTURE'):owner._prepare()
                lease.assert_not_called();off.assert_not_called();read.assert_not_called();start.assert_not_called()
if __name__=='__main__':unittest.main()
