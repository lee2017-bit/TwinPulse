# SPDX-License-Identifier: Apache-2.0
"""OFFLINE timing/immutable-publication guards, no ROS imports or hardware."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace as S
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'));sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from native_stream import freeze_frame
from teleop_ros import RosLink
from fleet_control import RobotControl
from teleop_contract import InputGate

class ResidualTests(unittest.TestCase):
    def test_json_compatible_recursive_immutable_snapshot(self):
        value={'beams':[{'distance_m':1.}], 'timing':{'receipt_end_s':1.}}
        frame=freeze_frame(value);self.assertIs(deepcopy(frame),frame)
        self.assertEqual(json.dumps(frame,sort_keys=True),json.dumps(value,sort_keys=True))
        with self.assertRaises(TypeError):frame['beams'][0]['distance_m']=0.
        with self.assertRaises(TypeError):frame['timing'].update(receipt_end_s=9.)
        value['timing']['receipt_end_s']=9.;self.assertEqual(frame['timing']['receipt_end_s'],1.)
    def link(self):
        link=RosLink.__new__(RosLink);link.sensor=S(header=S(stamp=S(sec=10,nanosec=0)),battery=11.6,button=0)
        link.sensor_t=link.guard_t=10.;link.node=S(get_clock=lambda:S(now=lambda:S(nanoseconds=10_050_000_000)),
            count_publishers=lambda topic:0 if topic=='cmd_vel' else 1)
        link.pub=S(get_subscription_count=lambda:1);return link
    def test_fresh_diagnostics_do_not_relax_existing_guard(self):
        link=self.link()
        with patch('teleop_ros.time.monotonic',return_value=10.05):link.fresh()
        self.assertEqual(link.fresh_diagnostic['reason'],'CURRENT')
        link.guard_t=9.
        with patch('teleop_ros.time.monotonic',return_value=10.05),self.assertRaisesRegex(ValueError,'TELEMETRY_STALE'):link.fresh()
        self.assertEqual(link.fresh_diagnostic['reason'],'GUARD_RECEIPT_STALE')
        link.guard_t=10.;link.node.get_clock=lambda:S(now=lambda:S(nanoseconds=10_300_000_000))
        with patch('teleop_ros.time.monotonic',return_value=10.05),self.assertRaisesRegex(ValueError,'BATTERY_BUTTON_OR_SOURCE_AGE'):link.fresh()
        self.assertEqual(link.fresh_diagnostic['reason'],'SENSOR_SOURCE_AGE')
    def test_recording_does_not_refresh_sensor_or_guard_receipt(self):
        link=self.link();link.rows=[];link.anchor=None;link._record=lambda *_,**kw:{'receipt_monotonic_ns':10_000_000_000}
        link.sensor.left_encoder=link.sensor.right_encoder=0;link.sensor.torque=True
        with patch('teleop_ros.time.monotonic',return_value=11.):
            link._sensor(link.sensor);link._guard(S(data='explicit_stop'))
        self.assertEqual(link.sensor_t,10.);self.assertEqual(link.guard_t,10.)
    def test_original_failed_check_survives_cleanup_fresh_success(self):
        link=self.link();link.guard_t=9.
        with patch('teleop_ros.time.monotonic',return_value=10.05):
            try:link.fresh()
            except ValueError as error:original=error.telemetry_diagnostic
            else:self.fail('stale guard must fail')
            link.guard_t=10.;link.fresh()
        self.assertEqual(link.fresh_diagnostic['reason'],'CURRENT')
        self.assertEqual(original['reason'],'GUARD_RECEIPT_STALE')
        self.assertEqual(original['checked_monotonic_s'],10.05)
        self.assertEqual(original['guard_receipt_s'],9.)
        self.assertEqual(original['sensor_receipt_s'],10.)
    def test_ready_pump_is_nonblocking_count_and_time_bounded(self):
        link=self.link();calls=[];link.base=S(poll=lambda:None)
        link.ros=S(spin_once=lambda node,timeout_sec:calls.append(timeout_sec))
        with patch('teleop_ros.time.monotonic',return_value=10.):link.drain_ready_control()
        self.assertEqual(calls,[0.]*8)
        calls.clear()
        with patch('teleop_ros.time.monotonic',side_effect=[10.,10.006]):link.drain_ready_control()
        self.assertEqual(calls,[0.])
    def test_publish_preflight_services_ready_guard_before_validation(self):
        link=self.link();link.guard_t=9.;link.persistent_manual=True
        link.sensor.torque=False;link.reason='explicit_stop'
        calls=[]
        def ready():calls.append('pump');link.guard_t=10.05
        link.drain_ready_control=ready
        with patch('teleop_ros.time.monotonic',return_value=10.05),self.assertRaisesRegex(ValueError,'GUARD_OR_TORQUE_STOP'):
            link.publish(.03,0.,.01)
        self.assertEqual(calls,['pump'])
        self.assertEqual(link.fresh_diagnostic['reason'],'CURRENT')
        # Receiving OFF during the pump must never authorize an output.
        self.assertFalse(link.sensor.torque)
    def test_ready_pump_does_not_bypass_real_outage_or_retime_source(self):
        link=self.link();link.guard_t=9.;link.persistent_manual=True
        link.drain_ready_control=lambda:None
        with patch('teleop_ros.time.monotonic',return_value=10.05),self.assertRaisesRegex(ValueError,'TELEMETRY_STALE'):
            link.publish(.03,0.,.01)
        self.assertEqual(link.guard_t,9.)
        self.assertEqual(link.sensor_t,10.)
        self.assertAlmostEqual(link.publication_diagnostic['source_created_s'],10.04)
        self.assertEqual(link.publication_diagnostic['phases'][-1]['name'],'FRESH_PREFLIGHT')
    def test_slow_output_stage_retains_original_input_and_never_publishes(self):
        link=self.link();now=[10.05];published=[]
        link.sensor.torque=True;link.reason='active'
        link.Twist=lambda:S(header=S(frame_id='',stamp=S(sec=0,nanosec=0)),
            twist=S(linear=S(x=0.),angular=S(z=0.)))
        link.pub.publish=published.append
        def slow_record(*_):now[0]+=.2
        with patch('teleop_ros.time.monotonic',side_effect=lambda:now[0]),patch('teleop_ros.RosLink._record',side_effect=slow_record),self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):
            link.publish(.03,0.,.2)
        self.assertEqual(published,[])
        trace=link.publication_diagnostic
        self.assertAlmostEqual(trace['source_created_s'],9.85)
        record=next(p for p in trace['phases'] if p['name']=='RAW_RECORD_ENQUEUE')
        self.assertAlmostEqual(record['ended_s']-record['started_s'],.2)
        self.assertEqual(trace['phases'][-1]['name'],'POST_RECORD_INPUT_AGE')
    def test_expired_gate_exception_keeps_clock_before_pause_clears_it(self):
        now=[1.];gate=InputGate(clock=lambda:now[0],persistent=True,recoverable=True)
        nonce=gate.challenge();gate.accept(dict(sequence=1,action='forward',challenge=nonce,age_ms=0))
        deadline=gate.deadline;created=gate.source_created;now[0]=deadline+.001
        try:gate.check()
        except ValueError as error:original=error.input_diagnostic
        else:self.fail('old lease must expire')
        self.assertEqual(gate.deadline,0.)
        self.assertIsNone(gate.source_created)
        self.assertEqual(original['deadline_s'],deadline)
        self.assertEqual(original['source_created_s'],created)
    def test_display_voltage_updates_on_fresh_failure_without_drive(self):
        control=RobotControl.__new__(RobotControl);control.clock=lambda:10.05;updates=[]
        link=self.link();link.spin=lambda *_:None;link.rows=[{'source_age_s':.3}]
        link.sensor.left_encoder=link.sensor.right_encoder=0;link.node.get_clock=lambda:S(now=lambda:S(nanoseconds=10_300_000_000))
        control.link=link;control._update=lambda **v:updates.append(v)
        control._pose=lambda:None
        with patch('teleop_ros.time.monotonic',return_value=10.05),self.assertRaisesRegex(ValueError,'BATTERY_BUTTON_OR_SOURCE_AGE'):control._tick()
        self.assertEqual(updates[0]['battery']['voltage_v'],11.6)
        self.assertEqual(updates[0]['battery']['sample_monotonic_s'],10.)
        self.assertEqual(updates[-1]['telemetry_diagnostic']['reason'],'SENSOR_SOURCE_AGE')
    def test_tick_first_check_drains_ready_guard_without_relaxing_source(self):
        control=RobotControl.__new__(RobotControl);control.clock=lambda:10.05;updates=[]
        link=self.link();link.persistent_manual=True;link.guard_t=9.;order=[]
        link.spin=lambda *_:order.append('spin')
        def ready():order.append('ready');link.guard_t=10.05
        link.drain_ready_control=ready;link.rows=[{'source_age_s':.3}]
        link.node.get_clock=lambda:S(now=lambda:S(nanoseconds=10_300_000_000))
        control.link=link;control._update=lambda **v:updates.append(v);control._pose=lambda:None
        with patch('teleop_ros.time.monotonic',return_value=10.05),self.assertRaisesRegex(ValueError,'BATTERY_BUTTON_OR_SOURCE_AGE'):
            control._tick()
        self.assertEqual(order,['spin','ready'])
        self.assertEqual(updates[-1]['telemetry_diagnostic']['reason'],'SENSOR_SOURCE_AGE')
        self.assertEqual(link.sensor_t,10.)
    def test_callback_source_clock_precedes_slow_sink_and_never_renews_header(self):
        link=self.link();metadata=[];clock=[10_000_000_000]
        link.node.get_clock=lambda:S(now=lambda:S(nanoseconds=10_050_000_000))
        def slow_sink(_topic,_msg,value):
            metadata.append(dict(value));clock[0]+=250_000_000
        link.record_sink=slow_sink
        with patch('teleop_ros.time.monotonic_ns',side_effect=lambda:clock[0]):
            result=link._record('sensor_state',link.sensor)
        self.assertEqual(result['receipt_monotonic_ns'],10_000_000_000)
        self.assertEqual(metadata[0]['source_stamp_ns'],10_000_000_000)
        self.assertEqual(metadata[0]['receipt_ros_now_ns'],10_050_000_000)
        self.assertEqual(metadata[0]['source_age_at_receipt_s'],.05)
        self.assertEqual(result['recording_elapsed_s'],.25)
        link.sensor_receipt_timing=result
        link.node.get_clock=lambda:S(now=lambda:S(nanoseconds=10_300_000_000))
        with patch('teleop_ros.time.monotonic',return_value=10.05),self.assertRaisesRegex(ValueError,'BATTERY_BUTTON_OR_SOURCE_AGE'):
            link.fresh()
        self.assertEqual(link.fresh_diagnostic['source_age_s'],.3)
        self.assertEqual(link.fresh_diagnostic['callback_timing']['source_age_at_receipt_s'],.05)
    def test_repeated_automatic_fault_burns_nonces_without_unbounded_epoch_churn(self):
        gate=InputGate(clock=lambda:10.,persistent=True,recoverable=True)
        before=gate.challenge();gate.pause('SENSOR_SOURCE_AGE',repeated_observation=True)
        self.assertEqual(gate.generation,1)
        between=gate.challenge();gate.pause('SENSOR_SOURCE_AGE',repeated_observation=True)
        self.assertEqual(gate.generation,1)
        for i,nonce in enumerate((before,between),1):
            with self.assertRaisesRegex(ValueError,'INPUT_CHALLENGE'):
                gate.accept(dict(sequence=i,action='watch',challenge=nonce,age_ms=0))
        nonce=gate.challenge();gate.accept(dict(sequence=3,action='watch',challenge=nonce,age_ms=0))
        gate.discard_idle_watch()
        gate.pause('SENSOR_SOURCE_AGE',repeated_observation=True)
        self.assertEqual(gate.generation,2) # Even an idle accepted watch is revoked.
        gate.pause('GUARD_RECEIPT_STALE',repeated_observation=True)
        self.assertEqual(gate.generation,3)
        for reason in ('OPERATOR_STOP','OPERATOR_STOP','FIELD_CONFIG_CHANGED','FIELD_ARMED_NEW_INPUT_REQUIRED'):
            old=gate.generation;gate.pause(reason);self.assertEqual(gate.generation,old+1)
    def test_repeated_pause_never_skips_release_retry_or_clearing_task(self):
        control=RobotControl.__new__(RobotControl);control.gate=InputGate(persistent=True,recoverable=True)
        control.guard=None;control.field_trial=None
        control.state=dict(control_state='DRIVING',reason=None);control._update=lambda **values:control.state.update(values)
        control.pause_sequence=0;control.context=dict(connection_epoch='test');control.emit=lambda *_:None;control.clock=lambda:1.
        control.link=S(enabled=True,sensor=S(torque=True),release=lambda:None)
        attempts=[]
        def release():
            attempts.append(1)
            if len(attempts)==1:raise ValueError('SERVICE_FAILED')
        control.link.release=release
        control.direction='forward';control.task={'active':True};control.drive_command={'active':True}
        with self.assertRaisesRegex(ValueError,'SERVICE_FAILED'):
            control._pause('SENSOR_SOURCE_AGE',repeated_observation=True)
        control._pause('SENSOR_SOURCE_AGE',repeated_observation=True)
        self.assertEqual(len(attempts),2);self.assertEqual(control.gate.generation,1)
        self.assertIsNone(control.direction);self.assertIsNone(control.task);self.assertIsNone(control.drive_command)

    def test_pause_retains_original_check_before_release_overwrites_it(self):
        control=RobotControl.__new__(RobotControl);control.gate=InputGate(persistent=True,recoverable=True)
        control.guard=None;control.field_trial=None;control.direction='forward';control.task=None;control.drive_command=None
        control.state=dict(control_state='DRIVING',reason=None);control._update=lambda **v:control.state.update(v)
        control.pause_sequence=0;control.context=dict(connection_epoch='test');events=[]
        control.emit=lambda kind,data:events.append((kind,data));control.clock=lambda:20.
        original=dict(reason='GUARD_RECEIPT_STALE',checked_monotonic_s=10.,guard_receipt_s=9.7)
        def release():original['reason']='CURRENT'
        control.link=S(enabled=True,sensor=S(torque=True),release=release)
        control._pause('TELEMETRY_STALE',fault_diagnostic=original)
        self.assertEqual(control.state['last_control_fault']['telemetry']['reason'],'GUARD_RECEIPT_STALE')
        self.assertEqual(events[-1][1]['fault_diagnostic']['checked_monotonic_s'],10.)
        self.assertTrue(events[-1][1]['zero_off_readback_confirmed'])

if __name__=='__main__':unittest.main()
