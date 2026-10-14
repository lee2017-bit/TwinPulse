# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No devices: exact worker orchestration with mocked ROS/base/board interfaces."""
from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'twinpulse_core/src'))
import runtime
import stationary
import teleop_worker as worker
import teleop_ros
from stop_policy import POLICY_SHA256


class ProtocolOutboxTests(unittest.TestCase):
    def test_blocked_peer_does_not_block_producer_and_latches_delivery_fault(self):
        entered=threading.Event();release=threading.Event();now=[0.]
        def writer(_):entered.set();release.wait(2)
        box=worker.ProtocolOutbox(writer,clock=lambda:now[0])
        try:
            box.send({'state':'READY','challenge':'original'})
            self.assertTrue(entered.wait(1))
            box.send({'state':'SESSION_EVENT'})
            now[0]=.201
            with self.assertRaisesRegex(ValueError,'PROTOCOL_DELIVERY_STALLED'):box.check()
            with self.assertRaisesRegex(ValueError,'PROTOCOL_DELIVERY_STALLED'):box.send({'state':'READY'})
        finally:release.set();box.close(timeout=1)

    def test_fifo_original_values_and_no_retimestamping(self):
        sent=[];box=worker.ProtocolOutbox(sent.append)
        value={'state':'READY','challenge':'original','sample_s':12.}
        box.send(value);value['challenge']='changed'
        box.send({'state':'FINISHED'})
        status=box.close(timeout=1)
        self.assertFalse(status['sender_alive']);self.assertIsNone(status['error'])
        self.assertEqual(sent,[{'state':'READY','challenge':'original','sample_s':12.},{'state':'FINISHED'}])

    def test_queue_and_byte_budget_are_explicit_failures(self):
        for cap,reason in ((4,'PROTOCOL_QUEUE_FULL'),(100,'PROTOCOL_BYTE_BUDGET')):
            entered=threading.Event();release=threading.Event()
            def writer(_):entered.set();release.wait(2)
            box=worker.ProtocolOutbox(writer,max_messages=cap,max_bytes=300 if cap==100 else 1024*1024)
            try:
                box.send({'value':'x'*70});self.assertTrue(entered.wait(1))
                with self.assertRaisesRegex(ValueError,reason):
                    for _ in range(8):box.send({'value':'x'*70})
            finally:release.set();box.close(timeout=1)

    def test_writer_failure_never_reports_delivery_success(self):
        failed=threading.Event()
        def writer(_):failed.set();raise OSError('simulated peer loss')
        box=worker.ProtocolOutbox(writer)
        box.send({'state':'READY'});self.assertTrue(failed.wait(1))
        status=box.close(timeout=1)
        self.assertEqual(status['error'],'PROTOCOL_WRITE_FAILED')
        self.assertEqual(status['sent_messages'],0)


class NavigationTopicTests(unittest.TestCase):
    def test_scan_count_uses_root_subscription_not_relative_namespace(self):
        calls=[];observations=[]
        link=teleop_ros.RosLink.__new__(teleop_ros.RosLink)
        link.node=SimpleNamespace(count_publishers=lambda topic:calls.append(topic) or (1 if topic=='/scan' else 0),
                                  get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=1)))
        link.navigation=SimpleNamespace(receive=lambda *args:observations.append(args))
        link._navigation('scan',object())
        self.assertEqual(calls,['/scan']);self.assertEqual(observations[0][-1],1)
        link._navigation('odom',object());self.assertEqual(calls,['/scan','odom'])


class LifecycleTests(unittest.TestCase):
    def test_operator_close_requires_both_ros_and_final_idle_confirmation(self):
        for ros_ok,idle_ok,expected in ((True,True,'OPERATOR_STOP'),(False,True,'FINAL_ROS_STOP_UNCONFIRMED'),
                                       (True,False,'FINAL_IDLE_UNCONFIRMED')):
            report,_,_=self.exercise('control',trial='OPERATOR_STOP',qualified=True,ros_stop_ok=ros_ok,final_ok=idle_ok)
            self.assertEqual(report['status'],expected)
            self.assertEqual(report['operation_status'],'OPERATOR_STOP')

    def exercise(self,mode,trial='STOP_POLICY_PASS',final_ok=True,qualified=False,consumed=False,legacy=False,ros_stop_ok=True,off_final_ok=True,mission_reviewed=True,journal_error=False,mission_failure=None):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            home=Path(folder);release=home/'current';release.mkdir();(home/'state').mkdir()
            if consumed:(home/'state'/('manual-trial-test-boot-'+'a'*64)).touch()
            profile={'manual_control_policy':'explicit_session_and_same_boot_release_stop_receipt'}
            if mode=='mission' and mission_reviewed:profile['autonomous_control_policy']='qualified_session_reviewed_planar_frames_v1'
            (release/'profile.json').write_text(json.dumps(profile))
            if qualified:(home/'state/manual-qualification.json').write_text(json.dumps({
                'schema':'manual-stop-1.0' if legacy else 'manual-stop-2.0',
                'policy_sha256':POLICY_SHA256,'boot_id':'test-boot','release_id':'a'*64,'status':'QUALIFIED'}))
            board={'status':'OBSERVED','torque_enabled':False,'wheel_velocity_raw':[0,0],
                   'command_bytes_zero':True,'near_board_protection':False,'encoders':[0,0]}
            events=[]; output=[]
            def control(*args,**kwargs):
                if journal_error:
                    kwargs['record']('accepted',sequence=1,action='watch',source_age_s=0.)
                    raise ValueError('SESSION_JOURNAL_WRITE_STALLED')
                return {'status':trial,'stop_assessment':{'status':'PASS' if trial=='STOP_POLICY_PASS' else 'FAIL'}}
            def read(_release,log,_fd):
                events.append('read-'+log.stem)
                if log.stem=='after' and not final_ok:raise ValueError('READ_FAILED')
                log.write_text('fake')
            def disarm(_release,log,_fd,**_):
                events.append('off')
                if log.stem=='final-off' and not off_final_ok:raise ValueError('HOST_DISCONNECT_TIMEOUT')
            import mission_runtime
            def run_mission(*_args,**kwargs):
                kwargs['consume']();events.append('mission_loop')
                if mission_failure is not None:raise mission_failure
                return {'status':trial,'mission_id':'a'*32,'mission_ticks':5}
            stack.enter_context(patch.object(mission_runtime,'receive_request',lambda *_:{'mission_id':'a'*32}))
            stack.enter_context(patch.object(mission_runtime,'run_mission',run_mission))
            class Link:
                rows=[]
                def __init__(self,_base,*,raw_path=None):
                    events.append('ros_construct')
                    self.received_counts={'odom':0,'scan':0,'/tf':0,'/tf_static':0}
                    self.moving_command_ns=[]
                def preflight(self):events.append('preflight')
                def bind_observations(self,context):self.context=context
                def observation_health(self):return {'motion_authorized':False,'context':self.context}
                def halt(self):
                    events.append('ros_halt')
                    if not ros_stop_ok:raise ValueError('FAKE_STOP_FAILURE')
                def close(self):events.append('ros_close')
            # Resolve imported robot_health solely to a fake parser; not hardware.
            stack.enter_context(patch.dict(sys.modules,{'robot_health':SimpleNamespace(parse_board_snapshot=lambda _:board)}))
            if mode in {'qualify_scan','control_scan','scan','mission'}:
                import isolated_ros_scan
                class Driver:
                    def __init__(self,_):
                        self.child=SimpleNamespace(poll=lambda:0)
                    def start(self):events.append('scan_start')
                    def running(self):return True
                    def stop(self):
                        events.append('scan_stop')
                        return {'sensor_stop':{'write_complete':True,'quiet_after_1s':True,
                                               'port_restored':True}}
                stack.enter_context(patch.object(isolated_ros_scan,'IsolatedRosScan',Driver))
                if mode in {'control_scan','scan','mission'}:
                    stack.enter_context(patch.object(worker,'prepare_manual_scan',
                        lambda link,output,driver,**kwargs:driver.start()))
            for target,name,value in [(worker,'__file__',str(release/'teleop_worker.py')),
                (worker,'boot_id',lambda:'test-boot'),(worker,'emit',output.append),
                (runtime,'HOME',home),(runtime,'ownership',lambda:nullcontext(SimpleNamespace(fileno=lambda:0))),
                (runtime,'verify_release',lambda _: {'source_id':'a'*64,'files':dict.fromkeys(['teleop_worker.py','teleop_contract.py','teleop_ros.py','teleop.sh','lidar_capture.py','stop_policy.py','local_navigation.py','ros_observations.py','navigation_binding.py','mission_runtime.py','mission_contract.py','isolated_ros_scan.py','robot_journal.py','observation_stream.py'])}),
                (runtime,'read_board',read),(runtime,'disarm_board',disarm),
                (stationary,'commands',lambda *a:(['fake'],[])),
                (stationary,'stop_child',lambda _:events.append('base_reaped') or {'escalation':'interrupt'}),
                (worker.subprocess,'Popen',lambda *a,**k:object()),(teleop_ros,'RosLink',Link),
                (worker,'InputStream',lambda **_:None),(worker,'control',control)]:
                stack.enter_context(patch.object(target,name,value))
            stack.enter_context(patch.object(worker.signal,'signal',lambda *a:None))
            stack.enter_context(patch.object(worker.signal,'alarm',lambda *a:None,create=True))
            # SIGALRM/SIGHUP absent on Windows, no actual signal installation in tests.
            stack.enter_context(patch.object(worker.signal,'SIGALRM',14,create=True))
            stack.enter_context(patch.object(worker.signal,'SIGHUP',1,create=True))
            worker.main(mode)
            receipt=home/'state/manual-qualification.json'
            return output[-1]['report'],events,json.loads(receipt.read_text()) if receipt.exists() else None

    def test_journal_fault_does_not_skip_halt_base_exit_and_independent_off(self):
        report,events,receipt=self.exercise('qualify',journal_error=True)
        self.assertEqual(report['first_failure']['code'],'SESSION_JOURNAL_WRITE_STALLED')
        self.assertEqual(report['status'],'FAILED');self.assertIsNone(receipt)
        self.assertTrue(report['cleanup_confirmed'])
        self.assertLess(events.index('ros_halt'),events.index('base_reaped'))
        self.assertGreater(events.index('read-after'),events.index('base_reaped'))
        self.assertEqual(report['local_journal_write']['accepted'],report['local_journal_write']['saved'])

    def test_missing_qualification_cannot_start_base(self):
        report,events,receipt=self.exercise('control')
        self.assertEqual(report['status'],'FAILED');self.assertNotIn('ros_construct',events)
        self.assertIsNone(receipt)

    def test_scan_only_needs_no_motion_receipt_but_owns_sensor_cleanup(self):
        report,events,receipt=self.exercise('scan',trial='OPERATOR_STOP')
        self.assertEqual(report['status'],'OPERATOR_STOP')
        self.assertIsNone(receipt)
        self.assertIn('scan_start',events);self.assertIn('scan_stop',events)
        self.assertTrue(report['sensor_cleanup_confirmed'])
        self.assertLess(events.index('scan_stop'),events.index('base_reaped'))

    def test_mission_entry_requires_opt_in_and_same_boot_stop_qualification(self):
        with self.assertRaisesRegex(ValueError,'AUTONOMOUS_PROFILE_NOT_REVIEWED'):
            self.exercise('mission',mission_reviewed=False)
        report,events,_=self.exercise('mission')
        self.assertEqual(report['status'],'FAILED');self.assertNotIn('ros_construct',events)
        self.assertNotIn('mission_loop',events)

    def test_mission_entry_keeps_independent_cleanup_and_failure_precedence(self):
        for final,ros,status in ((True,True,'MISSION_ARRIVED'),(False,True,'FINAL_IDLE_UNCONFIRMED'),
                                 (True,False,'FINAL_ROS_STOP_UNCONFIRMED')):
            report,events,_=self.exercise('mission',trial='MISSION_ARRIVED',qualified=True,final_ok=final,ros_stop_ok=ros)
            self.assertIn('mission_loop',events);self.assertEqual(report['status'],status)
            self.assertLess(events.index('preflight'),events.index('mission_loop'))
            self.assertTrue(report['sensor_cleanup_confirmed'])
            self.assertLess(events.index('scan_start'),events.index('mission_loop'))
            self.assertLess(events.index('scan_stop'),events.index('base_reaped'))
            self.assertGreater(events.index('read-after'),events.index('mission_loop'))

    def test_success_requires_final_independent_read_and_exact_binding(self):
        report,events,receipt=self.exercise('qualify')
        self.assertEqual(report['status'],'QUALIFIED')
        self.assertEqual(receipt['boot_id'],'test-boot');self.assertEqual(receipt['release_id'],'a'*64)
        self.assertLess(events.index('base_reaped'),events.index('read-after'))

    def test_combined_mode_reaps_sensor_before_final_board_read(self):
        report,events,receipt=self.exercise('qualify_scan')
        self.assertEqual(report['status'],'QUALIFIED')
        self.assertTrue(report['sensor_cleanup_confirmed'])
        self.assertLess(events.index('scan_stop'),events.index('base_reaped'))
        self.assertEqual(receipt['boot_id'],'test-boot')

    def test_supervised_manual_scan_has_one_owner_and_reaps_driver_before_board(self):
        report,events,_=self.exercise('control_scan',trial='OPERATOR_STOP',qualified=True)
        self.assertEqual(report['status'],'OPERATOR_STOP')
        self.assertTrue(report['sensor_cleanup_confirmed'])
        self.assertLess(events.index('scan_start'),events.index('scan_stop'))
        self.assertLess(events.index('scan_stop'),events.index('read-after'))
        denied,denied_events,_=self.exercise('control_scan',qualified=False)
        self.assertEqual(denied['reason'],'PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE')
        self.assertNotIn('scan_start',denied_events)

    def test_manual_scan_warmup_requires_live_scan_and_odom_before_control(self):
        class Link:
            received_counts={'scan':0,'odom':0}
            require_scan_fresh=False
            def spin(self,_):
                self.received_counts={'scan':3,'odom':3}
            def fresh(self):pass
            def fresh_scan(self):pass
        class Driver:
            def __init__(self):self.started=False
            def start(self):self.started=True
            def running(self):return self.started
        link,driver,output=Link(),Driver(),[]
        worker.prepare_manual_scan(link,output.append,driver)
        self.assertTrue(link.require_scan_fresh)
        self.assertEqual(output[0]['state'],'PREPARING')

    def test_manual_scan_warmup_rejects_missing_data_or_dead_driver(self):
        class Clock:
            t=0.
            def __call__(self):self.t+=1.;return self.t
        class Link:
            received_counts={'scan':0,'odom':0}
            def spin(self,_):pass
            def fresh(self):pass
        class Driver:
            def __init__(self,alive=True):self.alive=alive
            def start(self):pass
            def running(self):return self.alive
        with self.assertRaisesRegex(ValueError,'MANUAL_SCAN_OR_ODOM_NOT_READY'):
            worker.prepare_manual_scan(Link(),lambda *_:None,Driver(),Clock())
        with self.assertRaisesRegex(ValueError,'ISOLATED_SCAN_DRIVER_EARLY_EXIT'):
            worker.prepare_manual_scan(Link(),lambda *_:None,Driver(False),Clock())

    def test_final_read_failure_cannot_mint_qualification(self):
        report,_,receipt=self.exercise('qualify',final_ok=False)
        self.assertEqual(report['status'],'FINAL_IDLE_UNCONFIRMED');self.assertIsNone(receipt)
        self.assertEqual(report['cleanup_stage'],'independent_idle_read')
        self.assertEqual(report['cleanup_error'],'READ_FAILED')
        self.assertEqual(report['operation_status'],'STOP_POLICY_PASS')

    def test_failed_stop_never_mints_qualification(self):
        report,_,receipt=self.exercise('qualify',trial='SETTLING_FAIL')
        self.assertEqual(report['status'],'SETTLING_FAIL');self.assertIsNone(receipt)

    def test_passed_trial_and_failed_final_off_are_separate_no_receipt(self):
        report,events,receipt=self.exercise('qualify',off_final_ok=False)
        self.assertEqual(report['stop_assessment']['status'],'PASS')
        self.assertEqual(report['status'],'FINAL_IDLE_UNCONFIRMED')
        self.assertEqual(report['cleanup_stage'],'independent_torque_off')
        self.assertEqual(report['cleanup_error'],'HOST_DISCONNECT_TIMEOUT')
        self.assertNotIn('read-after',events);self.assertIsNone(receipt)

    def test_consumed_trial_rejected_before_ros_start(self):
        report,events,receipt=self.exercise('qualify',consumed=True)
        self.assertEqual(report['reason'],'TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED')
        self.assertNotIn('ros_construct',events)
        self.assertTrue(report['cleanup_confirmed'])
        self.assertIsNone(receipt)

    def test_old_receipt_cannot_authorize_new_policy(self):
        report,events,_=self.exercise('control',qualified=True,legacy=True)
        self.assertEqual(report['status'],'FAILED')
        self.assertNotIn('ros_construct',events)

    def test_ros_stop_failure_does_not_mint_receipt_even_if_final_off_passes(self):
        report,_,receipt=self.exercise('qualify',ros_stop_ok=False)
        self.assertEqual(report['status'],'FINAL_ROS_STOP_UNCONFIRMED')
        self.assertTrue(report['cleanup_confirmed'])
        self.assertIsNone(receipt)


class ReleaseTests(unittest.TestCase):
    """Execute production release with a deterministic sensor clock, no ROS."""
    def exercise(self, moving_until=.35, torque_stuck=False, stale=False, oscillate=False, service_fail=False, final=False):
        now=[0.];link=teleop_ros.RosLink.__new__(teleop_ros.RosLink)
        link.enabled=True;link.changed=0.;link.reason='active';link.rows=[]
        link.sensor=SimpleNamespace(left_encoder=0,right_encoder=0,torque=True)
        link.stop=object();link.Trigger=SimpleNamespace(Request=lambda:None)
        def call(*_):
            link.reason='explicit_stop'
            if service_fail:raise ValueError('SERVICE_FAILED')
        link.call=call
        def torque(_):link.sensor.torque=torque_stuck
        link.torque=torque
        def spin(dt):
            now[0]+=dt
            if now[0]<moving_until:
                link.changed=now[0]
                ticks=(100 if len(link.rows)%2 else 0) if oscillate else round(now[0]*40)
                link.sensor.left_encoder=link.sensor.right_encoder=ticks
            link.rows.append({'encoders':[link.sensor.left_encoder,link.sensor.right_encoder]})
        link.spin=spin
        def fresh():
            if stale:raise ValueError('TELEMETRY_STALE')
        link.fresh=fresh
        with patch.object(teleop_ros.time,'monotonic',lambda:now[0]):
            (link.halt if final else link.release)()
        self.assertFalse(link.enabled)
        return now[0]

    def test_release_allows_actual_stable_observation_not_short_fixed_sleep(self):
        elapsed=self.exercise()
        self.assertGreaterEqual(elapsed,.54);self.assertLess(elapsed,.9)

    def test_final_cleanup_criterion_unchanged(self):
        with self.assertRaisesRegex(ValueError,'STOP_READBACK_UNCONFIRMED'):self.exercise(final=True)

    def test_continued_motion_and_torque_never_confirm_idle(self):
        for kwargs in ({'moving_until':2.},{'torque_stuck':True}):
            with self.assertRaisesRegex(ValueError,'RELEASE_IDLE_UNCONFIRMED'):self.exercise(**kwargs)

    def test_oscillation_cannot_cancel_travel(self):
        with self.assertRaisesRegex(ValueError,'RELEASE_TRAVEL_EXCEEDED'):self.exercise(oscillate=True)

    def test_stale_telemetry_fails(self):
        with self.assertRaisesRegex(ValueError,'TELEMETRY_STALE'):self.exercise(stale=True)

    def test_service_failure_not_hidden_by_off_observation(self):
        with self.assertRaisesRegex(ValueError,'RELEASE_SERVICE_UNCONFIRMED'):self.exercise(service_fail=True)


if __name__=='__main__':unittest.main()
