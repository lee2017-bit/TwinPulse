# SPDX-License-Identifier: Apache-2.0
"""Supplementary pure/protocol replay. No robot/network/device activation."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from field_tests import checked_config, digest, frame_points, register_pair, FieldGuard, CASES
from native_stream import NativeDecoder, NativeStream
from fleet_control import RobotControl
from fleet_worker import checked_command, SOURCE_MEMBERS
from control_timing import INPUT_TTL_S


def config():
    return dict(schema='supervised-field-test-1.0',robot_id='b'*32,binding_sha256='a'*64,
        footprint_radius_m=.12,sensor_x_m=0.,sensor_y_m=0.,sensor_yaw_rad=0.,angle_sign=1,
        wheel_metres_per_tick=2*math.pi*.033/4096,wheel_separation_m=.16,
        provenance='reference',axes_reviewed=True)


def ring(now=1.,gap=1.):
    beams=[dict(angle_deg=float(i),distance_m=gap,quality=100,node_index=i,
        source_byte_cursor=i*3,valid_packet=True) for i in range(360)]
    return dict(complete=True,interval_fallback=False,frame_sequence=1,
        timing=dict(receipt_start_s=now-.1,receipt_end_s=now),source_byte_span=dict(start=0,end=1080),
        raw_sha256='a'*64,nodes_sha256='b'*64,beams=beams)


def persist(owner):
    until=time.monotonic()+2.
    while owner.field_pending and time.monotonic()<until:
        owner._poll_field_writes();time.sleep(.002)
    if owner.field_pending:raise AssertionError('real local writer ACK not received')


class FieldTests(unittest.TestCase):
    def test_offline_review_has_no_measured_promotion_and_strict_shape(self):
        c=checked_config(config(),robot_id='b'*32,binding_sha256='a'*64)
        self.assertEqual(c['provenance'],'reference');self.assertEqual(len(digest(c)),64)
        for key,value in [('axes_reviewed',False),('wheel_metres_per_tick',float('nan')),('robot_id','c'*32),('angle_sign',True)]:
            bad=dict(c);bad[key]=value
            with self.assertRaises(ValueError):checked_config(bad,robot_id='b'*32)
        with self.assertRaises(ValueError):checked_config(dict(c,extra='execute'))

    def test_guard_caps_original_input_ring_receipt_coverage_obstacle_and_replay(self):
        now=[1.];frame=ring();native=SimpleNamespace(latest_frame=lambda:frame)
        link=SimpleNamespace(sensor=SimpleNamespace(left_encoder=0,right_encoder=0),sensor_t=1.)
        guard=FieldGuard(config(),native,link,lambda:True,clock=lambda:now[0])
        guard(.03,0.,1.);self.assertEqual(guard.last_result['acquisition_timing'],'UNQUALIFIED')
        for v,w,stamp,reason in [(.05,0,1.,'SPEED_CAP'),(.03,0,1.-INPUT_TTL_S-.001,'ORIGINAL_INPUT')]:
            with self.assertRaisesRegex(ValueError,reason):guard(v,w,stamp)
        frame['beams'][0]['distance_m']=.20
        with self.assertRaisesRegex(ValueError,'PROXIMITY'):guard(.03,0.,1.)
        frame['beams'][0]['distance_m']=1.
        frame['beams']=[b for b in frame['beams'] if not 0<=b['angle_deg']<30]
        with self.assertRaisesRegex(ValueError,'COVERAGE'):guard(.03,0.,1.)
        frame.update(ring());frame['frame_sequence']=0
        with self.assertRaisesRegex(ValueError,'REPLAY'):guard(.03,0.,1.)

    def test_unknown_returns_and_stale_or_corrupt_frame_cannot_prove_clearance(self):
        for change,reason in [(dict(complete=False),'COMPLETE'),(dict(interval_fallback=True),'COMPLETE'),
                              (dict(timing=dict(receipt_start_s=0.,receipt_end_s=.2)),'STALE')]:
            with self.assertRaisesRegex(ValueError,reason):frame_points(dict(ring(),**change),config(),1.)
        frame=ring();frame['beams'][0]['valid_packet']=False
        with self.assertRaisesRegex(ValueError,'NODES'):frame_points(frame,config(),1.)

    def test_actual_wheel_reverse_or_jump_stops_all_command_directions(self):
        for v,w,deltas in [(.03,0.,(-5,-5)),(-.03,0.,(5,5)),(0.,.2,(5,-5)),(0.,-.2,(-5,5))]:
            now=[1.];frame=ring();link=SimpleNamespace(sensor_t=1.,sensor=SimpleNamespace(left_encoder=0,right_encoder=0))
            guard=FieldGuard(config(),SimpleNamespace(latest_frame=lambda:frame),link,lambda:True,clock=lambda:now[0])
            guard(v,w,1.);now[0]=1.05;link.sensor_t=1.05
            link.sensor.left_encoder,link.sensor.right_encoder=deltas
            with self.assertRaisesRegex(ValueError,'REVERSE_TO_COMMAND'):guard(v,w,1.05)
        link.sensor.left_encoder=link.sensor.right_encoder=10000
        with self.assertRaisesRegex(ValueError,'IMPLAUSIBLE_JUMP|REVERSE_TO_COMMAND'):guard(.03,0.,1.05)

    def test_pair_tracker_asymmetric_scene_without_wheel_seed(self):
        p=[(-2+i*.047,-1.) for i in range(85)]+[(2.,-1+i*.037) for i in range(80)]+[(-1.2+i*.017,1.8+i*.003) for i in range(60)]
        dx,dy,yaw=.018,-.009,.026;c,s=math.cos(yaw),math.sin(yaw)
        q=[(c*(x-dx)+s*(y-dy),-s*(x-dx)+c*(y-dy)) for x,y in p]
        fit=register_pair(p,q,deadline=100.,clock=lambda:1.)
        self.assertTrue(fit['independent']);self.assertEqual(fit['accuracy'],'UNQUALIFIED')
        self.assertAlmostEqual(fit['delta'][2],yaw,delta=.025)
        self.assertLess(math.dist(fit['delta'][:2],[dx,dy]),.04)
        with self.assertRaisesRegex(ValueError,'DEGENERATE'):
            register_pair([(i*.02,0.) for i in range(80)],q,deadline=100.,clock=lambda:1.)
        with self.assertRaisesRegex(ValueError,'DEADLINE'):register_pair(p,q,deadline=0.,clock=lambda:1.)

    def test_all_new_actions_in_reviewed_worker_and_exports_fixed(self):
        context=dict(operation_id='o',robot_id='b'*32,project_id='p',connection_epoch='c')
        for action in ('field_setup','field_arm','field_test','field_review'):
            packet=dict(schema='physical-live-command-1.0',**context,motion_epoch='m',request_id='r',sequence=1,action=action,payload={})
            self.assertEqual(checked_command(packet,context,0)['action'],action)
        for name in ('field-config.json','field-trials.json','field-stop.json','field-tracking.json'):self.assertIn(name,SOURCE_MEMBERS)

    def test_stationary_collection_needs_no_profile_no_base_and_review_preserves_machine_result(self):
        now=[1.];frame=ring();events=[]
        native=SimpleNamespace(latest_frame=lambda:frame,snapshot=lambda:dict(lidar_state='STREAMING'))
        with tempfile.TemporaryDirectory() as tmp:
            owner=RobotControl(dict(robot_id='b'*32,binding_sha256='a'*64),tmp,lambda *args:events.append(args),native,clock=lambda:now[0])
            owner.field_config=config()
            command=dict(action='field_test',payload=dict(case='stationary',confirmed=True),request_id='test')
            owner._field_command(command)
            for i in range(82):
                now[0]=1.+i*.1;frame.update(ring(now[0]));frame['frame_sequence']=i+1;owner._field_tick()
            persist(owner)
            self.assertEqual(owner.field_trials[0]['status'],'PASS');self.assertIsNone(owner.link);self.assertIsNone(owner.profile)
            self.assertIsNone(owner.field_receipt);self.assertFalse(owner.field_until)
            trial=owner.field_trials[0]
            owner._field_command(dict(action='field_review',payload=dict(trial_id=trial['trial_id'],observed='moved')))
            self.assertEqual(owner.field_trials[0]['status'],'PASS');self.assertEqual(trial['operator_verdict'],'INCONCLUSIVE')
            self.assertTrue(owner.field_writer.close()['complete'])
            self.assertTrue((Path(tmp)/'field-trials.json').is_file())

    def test_arm_while_moving_cannot_refresh_old_manual_input(self):
        now=[1.];owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(),clock=lambda:now[0])
        owner.field_config=config();owner.direction='forward';owner.link=SimpleNamespace(enabled=True)
        before=(owner.gate.sequence,owner.gate.source_created,owner.gate.deadline)
        with self.assertRaisesRegex(ValueError,'STOPPED_IDLE'):
            owner._field_command(dict(action='field_arm',payload={'confirmed':True}))
        self.assertEqual(before,(owner.gate.sequence,owner.gate.source_created,owner.gate.deadline))
    def test_idle_arm_rechecks_source_freshness_before_accepting_current_nonce(self):
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(latest_frame=lambda:ring()),clock=lambda:1.)
        owner.field_config=config()
        def stale():raise ValueError('BATTERY_BUTTON_OR_SOURCE_AGE')
        owner.link=SimpleNamespace(enabled=False,fresh=stale)
        nonce=owner.gate.challenge()
        packet=dict(action='field_arm',sequence=1,payload=dict(confirmed=True,
            challenge=nonce,source_age_ms=0,motion_generation=owner.gate.generation))
        with self.assertRaisesRegex(ValueError,'BATTERY_BUTTON_OR_SOURCE_AGE'):
            owner._field_command(packet)
        self.assertEqual(owner.gate.sequence,0);self.assertFalse(owner.field_until)
        self.assertIsNone(owner.direction);self.assertIsNone(owner.drive_command)

    def test_zero_collection_blocks_drive_and_stop_precedes_failed_recording(self):
        order=[];owner=RobotControl({},'.',lambda *_:None,SimpleNamespace())
        owner.field_trial=dict(status='RUNNING',case='stationary')
        with self.assertRaisesRegex(ValueError,'COLLECTION_ACTIVE'):
            owner._command(dict(action='drive',payload=dict(motion_generation=owner.gate.generation)))
        owner.field_trial=dict(status='RUNNING',case='forward',publications=1,trial_id='x')
        owner.link=SimpleNamespace(enabled=True,sensor=SimpleNamespace(torque=True),release=lambda:order.append('ZERO_OFF'))
        def failed(*_):order.append('RECORD');raise OSError('FULL')
        owner._field_write=failed
        owner._pause('OPERATOR_STOP')
        self.assertEqual(order,['ZERO_OFF','RECORD']);self.assertIsNone(owner.direction)
        self.assertEqual(owner.field_trial['status'],'INCONCLUSIVE')
        self.assertEqual(owner.field_evidence_fault,'FIELD_EVIDENCE_WRITE_FAILED')

    def test_proximity_human_clearance_cannot_pass_without_motion_and_readback(self):
        owner=RobotControl({},'.',lambda *_:None,SimpleNamespace())
        owner.field_trials=[dict(trial_id='x',case='proximity',status='INCONCLUSIVE',reason='FIELD_PROXIMITY_10CM',result={'publications':0,'stop_readback_confirmed':True})]
        owner._field_write=lambda *_:None
        owner._field_command(dict(action='field_review',payload=dict(trial_id='x',observed='stopped',clearance_m=.12)))
        self.assertEqual(owner.field_trials[0]['operator_verdict'],'INCONCLUSIVE')

    def test_speed_bound_bootstrap_receipt_does_not_certify_legacy_and_failure_revokes_prior(self):
        now=[1.];frame=ring();native=SimpleNamespace(latest_frame=lambda:frame)
        with tempfile.TemporaryDirectory() as tmp:
            owner=RobotControl(dict(robot_id='b'*32,binding_sha256='a'*64,boot_id='boot',release_id='release',worker_sha256='a'*64),
                tmp,lambda *_:None,native,clock=lambda:now[0])
            owner.field_config=config();owner.field_mode=True;owner.field_until=10.
            owner.link=SimpleNamespace(sensor_t=1.,sensor=SimpleNamespace(left_encoder=0,right_encoder=0))
            owner._install_guard();owner._cleanup=lambda:dict(cleanup_confirmed=True);owner._prepare=lambda:None
            for passed in (True,False):
                owner.field_until=10.;owner.field_trial=dict(trial_id='trial-'+str(passed),case='bootstrap_stop',status='RUNNING')
                c=dict(action='field_test',request_id='r',sequence=owner.gate.sequence+1,
                    payload=dict(confirmed=True,case='bootstrap_stop',challenge=owner.gate.challenge(),source_age_ms=0,motion_generation=owner.gate.generation))
                with patch('teleop_worker.qualify',return_value=dict(status='STOP_POLICY_PASS' if passed else 'STOP_POLICY_FAIL')) as qualify:
                    owner._field_bootstrap(c)
                persist(owner)
                self.assertEqual(qualify.call_args.kwargs['supervised_field_speed'],.03)
                self.assertIs(qualify.call_args.kwargs['post_arm_watch'],True)
                if passed:
                    self.assertEqual(owner.field_receipt['scope'],'FORWARD_WHEEL_WATCHDOG_OBSERVATION_ONLY')
                    self.assertEqual(owner.field_receipt['angular_stopping'],'NOT_MEASURED')
                    self.assertNotIn('QUALIFIED',str(owner.field_receipt))
                else:
                    self.assertIsNone(owner.field_receipt);self.assertEqual(owner.field_until,0.)
            self.assertTrue(owner.field_writer.close()['complete'])
            self.assertFalse((Path(tmp)/'qualification.json').exists())

    def test_actual_bootstrap_incoming_discards_prearm_generation_but_keeps_stop(self):
        for interrupt in (False,True):
            with self.subTest(interrupt=interrupt),tempfile.TemporaryDirectory() as tmp:
                now=[1.];events=[]
                owner=RobotControl(dict(robot_id='b'*32,binding_sha256='a'*64),tmp,
                    lambda kind,data:events.append((kind,data)),SimpleNamespace(latest_frame=lambda:ring()),clock=lambda:now[0])
                owner.field_config=config();owner.field_mode=True;owner.field_until=10.
                owner.link=SimpleNamespace(sensor_t=1.,sensor=SimpleNamespace(left_encoder=0,right_encoder=0))
                owner._install_guard();owner._cleanup=lambda:dict(cleanup_confirmed=True)
                owner.field_trial=dict(trial_id='arm-'+str(interrupt),case='bootstrap_stop',status='RUNNING')
                c=dict(action='field_test',request_id='trial',sequence=1,payload=dict(case='bootstrap_stop',confirmed=True,
                    challenge=owner.gate.challenge(),source_age_ms=0,motion_generation=owner.gate.generation))
                def protocol(link,incoming,output,gate,clock,**kw):
                    prior=gate.generation;gate.suspend_for_arm()
                    owner.queue.put(dict(action='watch',request_id='old',sequence=2,payload=dict(motion_generation=prior)))
                    self.assertIsNone(incoming.receive())
                    self.assertFalse(gate.active)
                    if interrupt:
                        owner.queue.put(dict(action='stop',request_id='stop',sequence=3,payload={}))
                        incoming.receive()
                        self.fail('Stop must interrupt the bootstrap before output')
                    output(dict(challenge=gate.challenge()))
                    owner.queue.put(dict(action='watch',request_id='new',sequence=3,payload=dict(
                        motion_generation=gate.generation,challenge=owner.state['watch_challenge'],source_age_ms=0)))
                    packet=incoming.receive();gate.accept(packet)
                    self.assertEqual(gate.sequence,3)
                    return dict(status='STOP_POLICY_FAIL')  # Not hardware qualification.
                with patch('teleop_worker.qualify',side_effect=protocol):owner._field_bootstrap(c)
                persist(owner)
                self.assertTrue(any(data.get('request_id')=='old' and data.get('status')=='REJECTED' for _,data in events))
                self.assertIsNone(owner.field_receipt)
                if interrupt:self.assertEqual(owner.field_trial['result']['receipt']['observed']['reason'],'FIELD_BOOTSTRAP_INTERRUPTED')
                self.assertTrue(owner.field_writer.close()['complete'])

    def test_motion_prerequisites_are_separate_and_no_restore_on_configuration(self):
        native=SimpleNamespace(latest_frame=lambda:ring(),snapshot=lambda:dict(lidar_state='STREAMING'))
        owner=RobotControl(dict(robot_id='b'*32,binding_sha256='a'*64),'.',lambda *_:None,native,clock=lambda:1.)
        self.assertIn('FIELD_CONFIG_REVIEW_REQUIRED',owner._field_blockers())
        owner.field_config=config();owner.link=SimpleNamespace(sensor_t=1.,enabled=False,sensor=SimpleNamespace(torque=False))
        owner.field_until=5.
        self.assertEqual(owner._field_blockers(),['FIELD_BOOTSTRAP_STOP_REQUIRED'])
        self.assertEqual(owner._field_blockers(receipt=False),[])
        for direction,wanted in [('forward',(.03,0.)),('backward',(-.03,0.)),('left',(0.,.2)),('right',(0.,-.2))]:
            owner.field_mode=True;self.assertEqual(owner._velocity(direction),wanted)
        owner._command(dict(action='stop',payload={},motion_epoch='new'))
        self.assertEqual(owner.field_until,5.)
        self.assertIsNone(owner.direction);self.assertFalse(owner.gate.active)

    def test_saved_native_original_rings_can_be_validated_without_pipeline_measurement(self):
        raw=(ROOT/'outputs/robot-obstacle-prior-20261017/sensor-only-raw-18/raw.bin').read_bytes()
        decoder=NativeDecoder();packets=[]
        for offset in range(0,len(raw),4096):packets.extend(decoder.feed(raw[offset:offset+4096],1.))
        batch=[];rings=0;start=False
        stream=NativeStream('.',lambda *_:None)
        for packet in packets:
            if packet['nodes'][0]['ring_start']:
                if batch:
                    stream._frame(batch,start);frame=stream.latest_frame()
                    if frame['complete'] and not frame['interval_fallback']:
                        frame_points(frame,config(),1.);rings+=1
                batch=[];start=True
            batch.append(packet)
        self.assertGreater(rings,20)
        # Saved byte provenance is real; replay receipt time is NOT live timing.
        self.assertEqual(stream.latest_frame()['timing']['basis'],'serial_receipt_unqualified')

if __name__=='__main__':unittest.main()
