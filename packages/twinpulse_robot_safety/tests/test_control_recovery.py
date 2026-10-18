# SPDX-License-Identifier: Apache-2.0
"""Original failure recovery / real local child process, robot OFF only."""
from pathlib import Path
import math
import os
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
from fleet_control import RobotControl,RosRecordDelivery
from field_tests import NativeTracker,frame_points,register_pair
from test_field_tests import config,ring,persist
from teleop_ros import RosLink


class RecoveryTests(unittest.TestCase):
    def test_snapshot_never_relabels_a_frozen_diagnostic_as_current(self):
        now=[1.];owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(),clock=lambda:now[0])
        original=dict(reason='CURRENT',checked_monotonic_s=1.,source_age_s=.034,
            sensor_receipt_age_s=.017,guard_receipt_age_s=.001)
        owner._update(telemetry_diagnostic=original)
        self.assertEqual(owner.snapshot()['telemetry_diagnostic']['reason'],'CURRENT')
        now[0]=1.3
        value=owner.snapshot()['telemetry_diagnostic']
        self.assertEqual(value['reason'],'DIAGNOSTIC_CHECK_STALE');self.assertIsNone(value['source_age_s'])
        self.assertEqual(value['last_check_values']['source_age_s'],.034)
        self.assertEqual(owner.state['telemetry_diagnostic'],original)

    @staticmethod
    def broken_field_writer():
        def fail(*_):raise ValueError('FIELD_EVIDENCE_STALLED')
        return SimpleNamespace(error='FIELD_EVIDENCE_STALLED',check=fail,append=fail,
            close=lambda:dict(complete=False,writer_reaped=True,error='FIELD_EVIDENCE_STALLED',pending=0))

    def test_latched_archive_failure_does_not_starve_run_loop_or_leave_trial_running(self):
        events=[];frame=ring();frame['timing']['acquisition_earliest_s']=None
        owner=RobotControl({},'.',lambda *v:events.append(v),
            SimpleNamespace(latest_frame=lambda:frame,snapshot=lambda:dict(lidar_state='STREAMING')),clock=lambda:1.)
        owner.field_config=config();owner.field_writer=self.broken_field_writer();owner.field_until=900.
        owner.field_trial=dict(trial_id='original',case='stationary',status='RUNNING',started_s=0.,frames=12)
        ticks=[]
        def tick():
            ticks.append(1)
            if len(ticks)==4:owner.cancel.set()
        owner._tick=tick
        owner._run()
        self.assertEqual(len(ticks),4)
        self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE')
        self.assertEqual(owner.field_trial['reason'],'FIELD_EVIDENCE_STALLED')
        self.assertEqual(owner.field_trial['frames'],12)
        self.assertEqual(owner.field_until,0.)
        self.assertEqual(owner.snapshot()['control_state'],'CLOSED')
        self.assertFalse(owner.cleanup_confirmed)

    def test_stop_after_failed_writer_never_propagates_archive_error_or_mints_receipt(self):
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(latest_frame=lambda:ring()),clock=lambda:1.)
        owner.field_config=config();owner.field_mode=True;owner.field_until=900.;owner.field_receipt={'old':'receipt'}
        owner.field_writer=self.broken_field_writer()
        owner.field_trial=dict(trial_id='original',case='forward',status='RUNNING',started_s=0.,frames=12)
        owner.direction='forward';owner.link=SimpleNamespace(enabled=False,sensor=SimpleNamespace(torque=False),sensor_t=1.)
        owner._pause('OPERATOR_STOP')
        self.assertIsNone(owner.direction);self.assertIsNone(owner.field_receipt)
        self.assertEqual(owner.field_trials[-1]['status'],'INCONCLUSIVE')
        self.assertEqual(owner.field_trial['result']['attempted_decision'],dict(status='CANCELLED',reason='OPERATOR_STOP'))
        self.assertIn('FIELD_EVIDENCE_STALLED',owner._field_blockers())
        with self.assertRaisesRegex(ValueError,'FIELD_EVIDENCE_STALLED'):owner._movement_ready()
        with self.assertRaisesRegex(ValueError,'FIELD_EVIDENCE_STALLED'):
            owner._field_command(dict(action='field_arm',payload=dict(confirmed=True)))

    def test_failed_durable_write_cannot_report_a_successful_trial(self):
        events=[];owner=RobotControl({},'.',lambda *v:events.append(v),SimpleNamespace(),clock=lambda:1.)
        owner.field_writer=self.broken_field_writer();owner.field_until=900.
        owner.field_trial=dict(trial_id='original',case='stationary',status='RUNNING',frames=80)
        owner._finish_field('PASS','ZERO_MOTION_NATIVE_COLLECTION',duration_s=8.)
        self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE')
        self.assertEqual(owner.field_trial['result']['attempted_decision']['status'],'PASS')
        self.assertEqual(owner.field_trial,owner.field_trials[-1])
        self.assertEqual(owner.field_until,0.)
        self.assertEqual(events[-1][1]['status'],'INCONCLUSIVE')
        self.assertEqual(events[-1][1]['trial']['status'],'INCONCLUSIVE')

    def test_final_safety_rechecks_archive_failure_not_just_ros_delivery(self):
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(),clock=lambda:1.)
        owner.field_writer=self.broken_field_writer()
        with self.assertRaisesRegex(ValueError,'FIELD_EVIDENCE_STALLED'):owner._safety()

    def test_native_guard_mid_call_archive_failure_prevents_actual_publish_boundary(self):
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(),clock=lambda:10.)
        writer=SimpleNamespace(error=None)
        def check():
            if writer.error:raise ValueError(writer.error)
        writer.check=check;owner.field_writer=writer
        link=RosLink.__new__(RosLink);link.fresh=lambda:None;link.sensor=SimpleNamespace(torque=True)
        link.reason='active';link.manual_speed_profile=True
        link.Twist=lambda:SimpleNamespace(header=SimpleNamespace(frame_id='',stamp=SimpleNamespace(sec=0,nanosec=0)),
            twist=SimpleNamespace(linear=SimpleNamespace(x=0.),angular=SimpleNamespace(z=0.)))
        link.node=SimpleNamespace(get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=10_000_000_000)))
        link.native_output_guard=lambda *_:setattr(writer,'error','FIELD_EVIDENCE_WRITE_FAILED')
        publications=[];link.pub=SimpleNamespace(publish=publications.append)
        with patch('teleop_ros.time.monotonic',return_value=10.),self.assertRaisesRegex(ValueError,'FIELD_EVIDENCE_WRITE_FAILED'):
            link.publish(.03,0.,0.,before_publish=owner._safety)
        self.assertEqual(publications,[])

    def test_owner_serialization_fault_cannot_be_hidden_by_writer_complete(self):
        frame=ring();frame['timing']['acquisition_earliest_s']=None
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(latest_frame=lambda:frame,snapshot=lambda:dict(lidar_state='OFF')),clock=lambda:1.)
        owner.field_evidence_fault='FIELD_EVIDENCE_WRITE_FAILED'
        owner.field_writer=SimpleNamespace(close=lambda:dict(complete=True,writer_reaped=True,error=None))
        owner.cancel.set();owner._run()
        self.assertFalse(owner.snapshot()['field_evidence']['complete'])
        self.assertEqual(owner.snapshot()['field_evidence']['error'],'FIELD_EVIDENCE_WRITE_FAILED')
        self.assertFalse(owner.cleanup_confirmed)

    def test_tracker_snapshot_never_reuses_old_pose_after_native_stream_or_sequence_change(self):
        frame=dict(stream_id='old',frame_sequence=10)
        tracker=NativeTracker.__new__(NativeTracker);tracker.lock=threading.Lock();tracker.clock=lambda:10.1
        tracker.native=SimpleNamespace(latest_frame=lambda:frame)
        tracker.result=dict(status='ESTIMATED',stream_id='old',frame_sequence=10,epoch='old-epoch',sample_s=10.,pose=[1,2,3])
        self.assertEqual(tracker.snapshot()['status'],'ESTIMATED')
        frame['stream_id']='new'
        self.assertIsNone(tracker.snapshot()['pose']);self.assertEqual(tracker.snapshot()['status'],'STALE')
        frame.update(stream_id='old',frame_sequence=1)
        self.assertIsNone(tracker.snapshot()['pose'])

    def test_stationary_preserves_full_interval_without_promoting_unknown_ring(self):
        now=[1.];frame=ring();native=SimpleNamespace(latest_frame=lambda:frame,snapshot=lambda:dict(lidar_state='STREAMING'))
        with tempfile.TemporaryDirectory() as tmp:
            owner=RobotControl({},tmp,lambda *_:None,native,clock=lambda:now[0]);owner.field_config=config()
            owner._field_command(dict(action='field_test',payload=dict(case='stationary',confirmed=True),request_id='original'))
            for i in range(82):
                now[0]=1.+i*.1;frame.update(ring(now[0]));frame['frame_sequence']=i+1
                if i in {10,40,70}:frame['complete']=False
                owner._field_tick()
                if i==10:self.assertEqual(owner.field_trial['status'],'RUNNING')
            persist(owner)
            trial=owner.field_trials[0]
            self.assertEqual(trial['status'],'INCONCLUSIVE');self.assertGreaterEqual(trial['result']['duration_s'],8.)
            self.assertEqual(trial['result']['invalid_frames'],3);self.assertGreater(trial['result']['frames'],60)
            self.assertIsNone(owner.link);self.assertIsNone(owner.field_receipt);owner.field_writer.close()

    def test_real_blocked_fsync_never_mints_pass_and_does_not_starve_observation(self):
        from field_tests import FieldEvidenceWriter
        entered,unblock=threading.Event(),threading.Event();now=[1.];events=[]
        with tempfile.TemporaryDirectory() as tmp:
            owner=RobotControl(dict(operation_id='original',connection_epoch='epoch'),tmp,
                lambda *v:events.append(v),SimpleNamespace(),clock=lambda:now[0])
            owner.field_trial=dict(trial_id='original',case='stationary',status='RUNNING',frames=80)
            owner.field_until=99.;ticks=[];owner._tick=lambda:ticks.append(1)
            real_fsync=os.fsync
            def blocked(fd):entered.set();unblock.wait(2.);real_fsync(fd)
            try:
                with patch('os.fsync',side_effect=blocked):
                    owner._finish_field('PASS','ZERO_MOTION_NATIVE_COLLECTION')
                    self.assertTrue(entered.wait(1.));self.assertEqual(owner.field_trial['status'],'PENDING_PERSISTENCE')
                    self.assertIsNone(owner.field_receipt)
                    now[0]=1.6
                    for _ in range(4):owner._cycle()
                    self.assertEqual(len(ticks),4);self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE')
                    self.assertEqual(owner.field_trial['reason'],'FIELD_EVIDENCE_STALLED')
                    self.assertEqual(owner.field_writer.status()['phase'],'FSYNC')
                    unblock.set();owner.field_writer.close();owner._poll_field_writes()
                self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE')
                self.assertFalse(any(v[1].get('status')=='PASS' for v in events))
                self.assertIsNone(owner.field_receipt);self.assertEqual(owner.field_until,0.)
            finally:
                unblock.set()
                if owner.field_writer:owner.field_writer.close()

    def test_ack_is_bound_to_exact_bytes_and_stop_cannot_restore_receipt(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as tmp:
            owner=RobotControl(dict(operation_id='original',connection_epoch='epoch'),tmp,lambda *_:None,SimpleNamespace(),clock=lambda:1.)
            owner.field_trial=dict(trial_id='original',case='bootstrap_stop',status='RUNNING',frames=0)
            owner.field_until=99.;prepared=[];owner._prepare=lambda:prepared.append(1)
            stop=owner._field_write('field-stop.json',dict(original='stop'))
            owner._finish_field('PASS','FORWARD_WHEEL_STOP_OBSERVATION',stop_write=stop,receipt=dict(scope='original'))
            owner.field_pending['original']['resume_generation']=owner.gate.generation
            owner._pause('OPERATOR_STOP')
            persist(owner)
            self.assertEqual(owner.field_trial['status'],'PASS')
            self.assertEqual(owner.field_trial['persistence']['state'],'COMMITTED')
            self.assertEqual(prepared,[]);self.assertIsNone(owner.field_receipt)
            for ack in owner.field_trial['persistence']['writes']:
                self.assertEqual(sha256((Path(tmp)/ack['name']).read_bytes()).hexdigest(),ack['sha256'])
            owner.field_writer.close()

    def test_new_context_rejects_old_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=RobotControl(dict(operation_id='old',connection_epoch='old'),tmp,lambda *_:None,SimpleNamespace(),clock=lambda:1.)
            owner.field_trial=dict(trial_id='old',case='stationary',status='RUNNING',frames=80)
            owner._finish_field('PASS','ZERO_MOTION_NATIVE_COLLECTION')
            owner.field_writer.close();owner.context=dict(operation_id='new',connection_epoch='new')
            owner._poll_field_writes()
            self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE')
            self.assertEqual(owner.field_evidence_fault,'FIELD_EVIDENCE_CONTEXT_CHANGED')
            self.assertIsNone(owner.field_receipt)

    def test_incomplete_close_terminalizes_pending_without_late_promotion(self):
        frame=ring();frame['timing']['acquisition_earliest_s']=None
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(latest_frame=lambda:frame,snapshot=lambda:dict(lidar_state='OFF')),clock=lambda:1.)
        token=dict(writer_id='a'*32,write_id=1,name='field-trials.json',sha256='b'*64)
        owner.field_writer=SimpleNamespace(error=None,append=lambda *_:token,
            receipt=lambda *_:None,close=lambda:dict(complete=False,writer_reaped=False,pending=1,error=None))
        owner.field_trial=dict(trial_id='original',case='stationary',status='RUNNING',frames=80)
        owner._finish_field('PASS','ZERO_MOTION_NATIVE_COLLECTION');owner.cancel.set();owner._run()
        self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE')
        self.assertEqual(owner.field_trial['reason'],'FIELD_EVIDENCE_CLOSE_UNCONFIRMED')
        self.assertFalse(owner.field_pending);self.assertFalse(owner.cleanup_confirmed)
        owner.field_writer.receipt=lambda *_:dict(token,state='COMMITTED');owner._poll_field_writes()
        self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE');self.assertIsNone(owner.field_receipt)

    def test_pending_result_blocks_a_second_trial(self):
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(),clock=lambda:1.)
        owner.field_trial=dict(trial_id='pending',case='stationary',status='PENDING_PERSISTENCE')
        with self.assertRaisesRegex(ValueError,'FIELD_TRIAL_ALREADY_RUNNING'):
            owner._field_command(dict(action='field_test',payload=dict(case='stationary',confirmed=True),request_id='new'))

    def test_latched_archive_and_stale_sensor_do_not_alternate_epochs_or_pause_events(self):
        events=[];owner=RobotControl({},'.',lambda *v:events.append(v),SimpleNamespace(),clock=lambda:1.)
        owner.field_writer=self.broken_field_writer()
        def stale():raise ValueError('TELEMETRY_STALE')
        owner._tick=stale
        for _ in range(100):owner._cycle()
        self.assertEqual(len([e for e in events if e[0]=='control_pause']),1)
        self.assertEqual(owner.state['reason'],'FIELD_EVIDENCE_STALLED')
        self.assertEqual(owner.state['secondary_control_fault'],'TELEMETRY_STALE')
        self.assertEqual(owner.gate.generation,1)

    def test_bootstrap_restore_requires_same_writer_order_exact_stop_and_complete_receipt(self):
        import json
        from twinpulse_core.field_persistence import restored_field_trials
        with tempfile.TemporaryDirectory() as tmp:
            context=dict(operation_id='original',connection_epoch='epoch')
            owner=RobotControl(context,tmp,lambda *_:None,SimpleNamespace(),clock=lambda:1.)
            owner.field_trial=dict(trial_id='original',case='bootstrap_stop',status='RUNNING',frames=0)
            stop_value=dict(scope='FORWARD_WHEEL_WATCHDOG_OBSERVATION_ONLY',status='OBSERVED')
            stop_token=owner._field_write('field-stop.json',stop_value)
            owner._finish_field('PASS','FORWARD_WHEEL_STOP_OBSERVATION',receipt=stop_value,stop_write=stop_token)
            closed=owner.field_writer.close();raw=(Path(tmp)/'field-trials.json').read_bytes()
            ledger=(Path(tmp)/'field-commits.jsonl').read_bytes();stop=(Path(tmp)/'field-stop.json').read_bytes()
            def result(data=ledger,stop_bytes=stop,receipt=closed):
                return restored_field_trials(raw,data,writer_complete=True,context=context,
                    writer_receipt=receipt,stop_raw=stop_bytes)[0]['status']
            self.assertEqual(result(),'PASS')
            self.assertEqual(result(stop_bytes=None),'INCONCLUSIVE')
            self.assertEqual(result(stop_bytes=stop+b' '),'INCONCLUSIVE')
            self.assertEqual(result(receipt=dict(closed,writer_id='0'*32)),'INCONCLUSIVE')
            self.assertEqual(result(receipt=dict(closed,last_write_id=3)),'INCONCLUSIVE')
            self.assertEqual(result(data=ledger.splitlines()[1]),'INCONCLUSIVE')
            entries=[json.loads(line) for line in ledger.splitlines()]
            entries[0],entries[1]=entries[1],entries[0]
            for index,entry in enumerate(entries,1):entry['write_id']=index
            self.assertEqual(result(data=b'\n'.join(json.dumps(entry).encode() for entry in entries)),'INCONCLUSIVE')

    def test_terminal_notification_failure_cannot_leave_pending_for_late_promotion(self):
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(),clock=lambda:1.)
        trial=dict(trial_id='original',case='stationary',status='PENDING_PERSISTENCE',decision=dict(status='PASS',reason='candidate'))
        owner.field_trial=trial;owner.field_trials=[dict(trial)]
        owner.field_pending['original']=dict(trial=trial,tokens=[])
        def fail(*_):raise OSError('OUTBOX')
        owner.emit=fail;owner._fail_pending_fields('FIELD_EVIDENCE_STALLED');owner._poll_field_writes()
        self.assertEqual(trial['status'],'INCONCLUSIVE');self.assertFalse(owner.field_pending)

    def test_writer_itself_latches_late_commit_even_without_owner_polling(self):
        from field_tests import FieldEvidenceWriter
        entered,unblock=threading.Event(),threading.Event();now=[1.];real_fsync=os.fsync
        with tempfile.TemporaryDirectory() as tmp:
            writer=FieldEvidenceWriter(tmp,clock=lambda:now[0])
            def blocked(fd):entered.set();unblock.wait(2.);real_fsync(fd)
            try:
                with patch('os.fsync',side_effect=blocked):
                    token=writer.append('field-config.json',dict(original=True));self.assertTrue(entered.wait(1.))
                    now[0]=1.6;unblock.set();closed=writer.close()
                self.assertFalse(closed['complete']);self.assertEqual(closed['error'],'FIELD_EVIDENCE_STALLED')
                with self.assertRaisesRegex(ValueError,'FIELD_EVIDENCE_STALLED'):writer.receipt(token)
            finally:unblock.set();writer.close()

    def test_exported_trial_resolves_only_with_exact_ack_and_complete_writer(self):
        from twinpulse_core.field_persistence import restored_field_trials
        with tempfile.TemporaryDirectory() as tmp:
            context=dict(operation_id='original',connection_epoch='epoch')
            owner=RobotControl(context,tmp,lambda *_:None,SimpleNamespace(),clock=lambda:1.)
            owner.field_trial=dict(trial_id='original',case='stationary',status='RUNNING',frames=80)
            owner._finish_field('PASS','ZERO_MOTION_NATIVE_COLLECTION');closed=owner.field_writer.close()
            raw=(Path(tmp)/'field-trials.json').read_bytes();ledger=(Path(tmp)/'field-commits.jsonl').read_bytes()
            self.assertEqual(restored_field_trials(raw,ledger,writer_complete=closed['complete'],context=context,writer_receipt=closed)[0]['status'],'PASS')
            self.assertEqual(restored_field_trials(raw,ledger,writer_complete=False,context=context)[0]['status'],'INCONCLUSIVE')
            self.assertEqual(restored_field_trials(raw+b' ',ledger,writer_complete=True,context=context,writer_receipt=closed)[0]['status'],'INCONCLUSIVE')
            self.assertEqual(restored_field_trials(raw,ledger,writer_complete=True,context=context,
                writer_receipt=dict(closed,writer_id='0'*32))[0]['status'],'INCONCLUSIVE')

    def test_diagnostic_zero_collection_can_start_on_unknown_ring_without_motion_authority(self):
        frame=ring();frame['complete']=False
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(latest_frame=lambda:frame,snapshot=lambda:dict(lidar_state='STREAMING')),clock=lambda:1.)
        owner.field_config=config();owner._field_command(dict(action='field_test',payload=dict(case='stationary',confirmed=True),request_id='diagnostic'))
        self.assertEqual(owner.field_trial['status'],'RUNNING');self.assertIsNone(owner.field_receipt)
        owner._field_tick();self.assertEqual(owner.field_trial['invalid_frames'],1)
        self.assertIsNone(owner.link);self.assertIsNone(owner.direction)

    def test_ros_enqueue_does_not_wait_for_serialization_and_preserves_order_clock_and_bytes(self):
        entered,unblock=threading.Event(),threading.Event();events=[]
        def serialize(message):entered.set();unblock.wait(1);return message
        delivery=RosRecordDelivery(lambda kind,data:events.append((kind,data)),serialize,{'odom':'test/Odom'})
        began=time.monotonic();delivery('odom',b'original',{'receipt_monotonic_ns':10_000_000_000,'sequence':7})
        self.assertTrue(entered.wait(.5));self.assertLess(time.monotonic()-began,.15)
        delivery('odom',b'second',{'receipt_monotonic_ns':11_000_000_000,'sequence':8})
        self.assertEqual(delivery.status()['accepted'],2);self.assertEqual(delivery.status()['saved'],0)
        unblock.set();status=delivery.close();self.assertTrue(status['worker_reaped']);self.assertIsNone(status['error'])
        self.assertEqual(status['saved'],2);self.assertEqual([r[1]['offset'] for r in events],[0,8])
        self.assertEqual([r[1]['receipt_start_s'] for r in events],[10.,11.])
        self.assertEqual(events[0][1]['base64'],'b3JpZ2luYWw=')

    def test_ros_serialization_failure_latches_instead_of_silent_loss(self):
        def broken(_):raise ValueError('CDR_FAILURE')
        delivery=RosRecordDelivery(lambda *_:None,broken,{'odom':'test/Odom'})
        delivery('odom',b'x',{'receipt_monotonic_ns':1,'sequence':1})
        end=time.monotonic()+1
        while not delivery.error and time.monotonic()<end:time.sleep(.005)
        with self.assertRaisesRegex(ValueError,'CDR_FAILURE'):delivery.check()
        self.assertEqual(delivery.close()['saved'],0)

    def test_icp_runs_in_separate_process_with_exact_same_fit_and_bounded_cleanup(self):
        native=SimpleNamespace(latest_frame=lambda:None)
        tracker=NativeTracker(native,config())
        p=[(-2+i*.047,-1.) for i in range(85)]+[(2.,-1+i*.037) for i in range(80)]+[(-1.2+i*.017,1.8+i*.003) for i in range(60)]
        dx,dy,yaw=.018,-.009,.026;c,s=math.cos(yaw),math.sin(yaw)
        q=[(c*(x-dx)+s*(y-dy),-s*(x-dx)+c*(y-dy)) for x,y in p]
        try:
            self.assertNotEqual(tracker.process.pid,os.getpid())
            expected=register_pair(p,q,deadline=time.monotonic()+.08)
            # Startup is not part of a frame's compute budget. Warm the child
            # before sending a job so this test measures the fixed computation.
            time.sleep(.35)
            actual=tracker._fit(p,q);self.assertEqual(actual,expected)
            self.assertLessEqual(tracker.compute_timing['compute_elapsed_s'],.08)
            self.assertEqual(tracker.compute_timing['job_id'],1)
        finally:
            self.assertEqual(tracker.close(),dict(worker_reaped=True,thread_reaped=True))

if __name__=='__main__':unittest.main()
