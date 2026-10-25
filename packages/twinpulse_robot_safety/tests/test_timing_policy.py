# SPDX-License-Identifier: Apache-2.0
"""Timing-contract boundaries and recorded failure rechecks; no hardware."""
from pathlib import Path
import hashlib
import json
import math
import re
import sys
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from control_timing import INPUT_TTL_S,INPUT_TTL_MS,ODOM_SAMPLE_INTERVAL_S,TIMING_POLICY
from teleop_contract import InputGate,MotionPaused
from fleet_control import RobotControl
from twinpulse_core.local_navigation import checked_command


class TimingPolicyTests(unittest.TestCase):
    def test_shared_wire_policy_and_other_limits_are_explicit(self):
        self.assertEqual((INPUT_TTL_S,INPUT_TTL_MS,ODOM_SAMPLE_INTERVAL_S),(.35,350,.3))
        text=(ROOT/'apps/twinpulse-web/src/robot-control-timing.ts').read_text()
        self.assertEqual(int(re.search(r'CONTROL_INPUT_TTL_MS=(\d+)',text)[1]),INPUT_TTL_MS)
        limits=TIMING_POLICY['limits']
        for key,value in [('ros_source',.2),('ros_receipt',.2),('native_receipt',.35),
                          ('cpp_output_guard',.4),('operator_presence',.5),('icp_compute',.08)]:
            self.assertEqual(limits[key]['seconds'],value)
        self.assertFalse(TIMING_POLICY['adaptive'])

    def test_original_input_boundaries_no_new_lifetime_on_receive(self):
        for age in (.249,.25,.3,.349999,.35,.350001):
            with self.subTest(age=age):
                now=[0.];gate=InputGate(lambda:now[0]);nonce=gate.challenge();now[0]=age
                packet=dict(sequence=1,action='forward',challenge=nonce,age_ms=0)
                if age<.35:
                    gate.accept(packet)
                    self.assertEqual(gate.source_created,0.);self.assertEqual(gate.deadline,.35)
                else:
                    with self.assertRaisesRegex(ValueError,'INPUT_EXPIRED'):gate.accept(packet)

    def test_stop_burns_old_nonce_and_expired_watch_cannot_resume(self):
        now=[0.];gate=InputGate(lambda:now[0],persistent=True,recoverable=True)
        old=gate.challenge();gate.accept(dict(sequence=1,action='left',challenge=old,age_ms=0))
        gate.accept(dict(sequence=1,action='stop',challenge=None,age_ms=0))
        with self.assertRaisesRegex(ValueError,'INPUT_CHALLENGE'):
            gate.accept(dict(sequence=2,action='left',challenge=old,age_ms=0))
        nonce=gate.challenge();now[0]=.350001
        with self.assertRaisesRegex(ValueError,'INPUT_EXPIRED'):
            gate.accept(dict(sequence=2,action='watch',challenge=nonce,age_ms=0))
        self.assertFalse(gate.active)

    def test_output_boundary_accepts_300ms_but_not_350ms_original_input(self):
        self.assertTrue(checked_command(.03,0,.3,None,1.,require_scan=False)['allowed'])
        for age in (.35,.351,float('nan'),-.001):
            self.assertFalse(checked_command(.03,0,age,None,1.,require_scan=False)['allowed'])

    def test_pruned_challenge_refusal_has_bound_secret_free_original_diagnostic(self):
        now=[0.];gate=InputGate(lambda:now[0],persistent=True,recoverable=True)
        nonce=gate.challenge();now[0]=1.;gate.challenge()
        with self.assertRaisesRegex(ValueError,'^INPUT_CHALLENGE$') as caught:
            gate.accept(dict(sequence=1,action='forward',challenge=nonce,age_ms=0))
        diagnostic=caught.exception.input_diagnostic
        self.assertEqual(diagnostic['challenge_fingerprint_sha256'],hashlib.sha256(nonce.encode()).hexdigest())
        self.assertEqual((diagnostic['generation'],diagnostic['checked_s'],diagnostic['retained_challenges']),(0,1.,1))
        self.assertNotIn(nonce,json.dumps(diagnostic));self.assertFalse(gate.active)
        gate.pause('INPUT_CHALLENGE')
        self.assertEqual(gate.generation,1)
        self.assertEqual(diagnostic['generation'],0)

    def test_consumed_or_stop_revoked_challenge_remains_rejected_without_retry(self):
        for stop in (False,True):
            with self.subTest(stop=stop):
                gate=InputGate(lambda:0.,persistent=True,recoverable=True)
                nonce=gate.challenge()
                gate.accept(dict(sequence=1,action='watch',challenge=nonce,age_ms=0))
                gate.discard_idle_watch()
                if stop:gate.accept(dict(sequence=2,action='stop',challenge=None,age_ms=0))
                generation=gate.generation
                with self.assertRaisesRegex(ValueError,'^INPUT_CHALLENGE$') as caught:
                    gate.accept(dict(sequence=3,action='forward',challenge=nonce,age_ms=0))
                self.assertEqual(caught.exception.input_diagnostic['generation'],generation)
                self.assertFalse(gate.active);self.assertEqual(gate.deadline,0.)

    def test_malformed_challenge_diagnostic_cannot_mask_original_refusal(self):
        for nonce in (None,[],{},'\ud800','x'*24):
            with self.subTest(nonce=repr(nonce)):
                gate=InputGate(lambda:0.)
                with self.assertRaisesRegex(ValueError,'^INPUT_CHALLENGE$') as caught:
                    gate.accept(dict(sequence=1,action='forward',challenge=nonce,age_ms=0))
                self.assertIsNone(caught.exception.input_diagnostic['challenge_fingerprint_sha256'])

    def tick(self,previous,pose):
        published=[];owner=RobotControl({},'.',lambda *_:None,SimpleNamespace(),clock=lambda:pose['sample_s']+.001)
        owner.field_mode=True;owner._safety=lambda:None;owner.gate.check=lambda:None;owner._pose=lambda:pose
        owner.link=SimpleNamespace(sensor=None,enabled=True,spin=lambda _:None,fresh=lambda:None,
            publish=lambda *a,**kw:published.append(a) or {})
        owner.task=dict(origin=previous,previous_pose=previous,direction='left',rotation=0.,amount=math.tau,deadline=1e9)
        owner.direction='left';owner.drive_command=dict(action='task',request_id='offline',motion_epoch='current')
        owner.gate.source_created=pose['sample_s'];owner._velocity=lambda _:(0.,.2)
        owner.guard=SimpleNamespace(last_result={},progress={})
        owner._tick()
        return owner,published

    def test_odom_interval_and_jump_have_separate_boundaries(self):
        old=dict(x=0.,y=0.,yaw=0.,frame_id='odom',sample_s=0.)
        for dt in (.199,.2,.207084908,.299999,.3):
            owner,published=self.tick(old,dict(old,sample_s=dt,yaw=.2*dt))
            self.assertEqual(len(published),1)
            self.assertEqual(owner.snapshot()['odom_interval']['limit_s'],.3)
        for dt in (.300001,.4):
            with self.assertRaisesRegex(MotionPaused,'TASK_ODOM_SAMPLE_GAP'):
                self.tick(old,dict(old,sample_s=dt,yaw=.2*dt))
        with self.assertRaisesRegex(MotionPaused,'TASK_ODOM_TIME_INVALID'):
            self.tick(old,dict(old,sample_s=-.001))
        for pose in (dict(old,sample_s=.1,yaw=1.),dict(old,sample_s=.1,x=1.)):
            with self.assertRaisesRegex(MotionPaused,'TASK_ODOM_JUMP'):self.tick(old,pose)

    def test_exact_original_failure_times_and_geometry_under_new_policy(self):
        directory=ROOT/'outputs/robot-powered-20261020-current07/raw'
        if not directory.exists():self.skipTest('Private original recording not shipped with source')
        receipt=json.loads((directory/'receipt.json').read_text())
        entry=next(s for s in receipt['segments'] if s['path']=='events-00011.jsonl')
        raw=(directory/entry['path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['sha256'])
        event=json.loads(raw.splitlines()[1299]);data=event['data']
        self.assertAlmostEqual(data['pose']['sample_s']-data['task']['previous_pose']['sample_s'],.207084908,places=8)
        owner,published=self.tick(data['task']['previous_pose'],data['pose'])
        self.assertEqual(len(published),1)
        self.assertAlmostEqual(owner.task['rotation'],.0426007509231569)
        # Original historical deadline failure remains a failure; this only
        # rechecks its recorded elapsed time against the newly approved policy.
        age=2959.141390726-2958.887241402
        self.assertGreater(age,.25);self.assertLess(age,INPUT_TTL_S)


if __name__=='__main__':unittest.main()
