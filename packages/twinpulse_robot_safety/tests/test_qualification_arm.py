# SPDX-License-Identifier: Apache-2.0
"""Supplementary admission regression; no network, ROS, motor or robot calls."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from collections import deque
import math

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'twinpulse_core/src'))
from control_timing import INPUT_TTL_S
from teleop_contract import InputGate
from teleop_worker import wait_for_post_arm_watch,qualify
from stop_policy import MM_PER_TICK


class QualificationArmTests(unittest.TestCase):
    def make(self):
        now=[1.]
        gate=InputGate(lambda:now[0],persistent=True,recoverable=True)
        gate.accept(dict(sequence=1,action='qualify',challenge=gate.challenge(),age_ms=0))
        old_generation=gate.generation
        gate.suspend_for_arm()
        now[0]+=.30  # Preparation consumes time, while no output occurs.
        link=SimpleNamespace(spin=lambda _:now.__setitem__(0,now[0]+.01),fresh=lambda:None)
        return now,gate,link,old_generation

    def test_slow_arm_requires_new_watch_without_restamping_old_input(self):
        now,gate,link,old=self.make();packets=[]
        def output(value):
            packets.append(dict(sequence=2,action='watch',challenge=value['challenge'],age_ms=0))
        wait_for_post_arm_watch(link,SimpleNamespace(receive=lambda:packets.pop(0)),output,gate,lambda:now[0])
        self.assertEqual(gate.generation,old+1)
        self.assertEqual(gate.source_created,1.30)
        self.assertAlmostEqual(gate.deadline,1.30+INPUT_TTL_S)
        now[0]=gate.deadline+.001
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):gate.check()

    def test_missing_post_arm_watch_never_grants_input(self):
        now,gate,link,_=self.make()
        with self.assertRaisesRegex(ValueError,'FRESH_POST_ARM_INPUT_REQUIRED'):
            wait_for_post_arm_watch(link,SimpleNamespace(receive=lambda:None),lambda _:None,gate,lambda:now[0])
        self.assertFalse(gate.active)
        self.assertIsNone(gate.source_created)

    def test_stop_interrupts_before_publication(self):
        now,gate,link,_=self.make()
        with self.assertRaisesRegex(ValueError,'TRIAL_INTERRUPTED_BEFORE_PUBLICATION'):
            wait_for_post_arm_watch(link,SimpleNamespace(receive=lambda:dict(sequence=2,action='force_stop',challenge=None,age_ms=0)),
                lambda _:None,gate,lambda:now[0])
        self.assertFalse(gate.active)

    def test_expired_watch_is_not_renewed(self):
        now,gate,link,_=self.make();packets=[]
        def output(value):
            packets.append(dict(sequence=2,action='watch',challenge=value['challenge'],age_ms=0))
            now[0]+=INPUT_TTL_S+.001
        with self.assertRaisesRegex(ValueError,'FRESH_POST_ARM_INPUT_REQUIRED'):
            wait_for_post_arm_watch(link,SimpleNamespace(receive=lambda:packets.pop(0)),output,gate,lambda:now[0])
        self.assertFalse(gate.active)

    def test_fault_keeps_original_deadline_after_authority_is_discarded(self):
        now,gate,link,_=self.make()
        nonce=gate.challenge();now[0]+=.18
        gate.accept(dict(sequence=2,action='watch',challenge=nonce,age_ms=10))
        deadline=gate.deadline;now[0]=deadline+.001
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):gate.check()
        self.assertFalse(gate.active);self.assertIsNone(gate.source_created)
        self.assertEqual(gate.first_fault['deadline_s'],deadline)
        self.assertEqual(gate.first_fault['last_admission']['issued_s'],1.3)
        self.assertAlmostEqual(gate.first_fault['last_admission']['remaining_s'],INPUT_TTL_S-.19)
        self.assertNotIn('challenge',str(gate.first_fault))

    def trial(self,relay_delay=.025,silence_at=None):
        """Actual qualify/gate logic, deterministic transport and encoder model.

        Modelled samples are supplementary; they never create a device receipt.
        """
        now=[1.];pending=deque();sequence=[1];phases=[];sent=[];last=[None];ticks=[0.]
        gate=InputGate(lambda:now[0],persistent=True,recoverable=True)
        gate.accept(dict(sequence=1,action='qualify',challenge=gate.challenge(),age_ms=0))
        link=SimpleNamespace(sensor=SimpleNamespace(left_encoder=0,right_encoder=0,torque=True),reason='active',rows=[])
        def spin(_):
            now[0]+=.01
            if last[0] is not None:
                link.reason='command_timeout' if now[0]-last[0]>=.4 else 'active'
                if link.reason=='active':ticks[0]+=.03*.01/(MM_PER_TICK/1000)
            link.sensor.left_encoder=link.sensor.right_encoder=round(ticks[0])
            link.rows.append(dict(t=now[0],encoders=[round(ticks[0])]*2,torque=True,source_age_s=.01))
        def output(value):
            if silence_at is None or now[0]<silence_at:
                sequence[0]+=1
                pending.append((now[0]+relay_delay,dict(sequence=sequence[0],action='watch',challenge=value['challenge'],age_ms=0)))
        def receive():return pending.popleft()[1] if pending and pending[0][0]<=now[0] else None
        def publish(*_):last[0]=now[0];sent.append(now[0])
        link.enable=lambda:now.__setitem__(0,now[0]+.30)
        link.spin=spin;link.fresh=lambda:None;link.publish=publish
        result=None;failure=None
        try:result=qualify(link,SimpleNamespace(receive=receive),output,gate,lambda:now[0],
            supervised_field_speed=.03,post_arm_watch=True,
            diagnostic=lambda phase:phases.append(dict(phase=phase,**gate.timing())))
        except ValueError as exc:failure=str(exc)
        return result,failure,gate,phases,sent

    def test_actual_qualification_loop_keeps_current_windows_until_stop_observation(self):
        result,failure,gate,phases,sent=self.trial()
        self.assertIsNone(failure);self.assertEqual(result['status'],'STOP_POLICY_PASS')
        self.assertGreater(len(sent),5)
        self.assertGreater(len(phases),30)
        self.assertEqual(result['stop_assessment']['limits']['max_sample_gap_s'],.1)

    def test_same_loop_rejects_real_gap_without_renewing_or_creating_stop_receipt(self):
        result,failure,gate,phases,sent=self.trial(silence_at=1.65)
        self.assertIsNone(result);self.assertEqual(failure,'INPUT_DEADLINE_EXPIRED')
        self.assertIsNotNone(gate.first_fault);self.assertFalse(gate.active)
        self.assertGreater(len(sent),0)

    def test_same_loop_rejects_delayed_nonce_before_any_publication(self):
        result,failure,gate,phases,sent=self.trial(relay_delay=INPUT_TTL_S+.01)
        self.assertIsNone(result);self.assertEqual(failure,'FRESH_POST_ARM_INPUT_REQUIRED')
        self.assertEqual(sent,[])


if __name__=='__main__':unittest.main()
