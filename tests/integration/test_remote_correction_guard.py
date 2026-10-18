# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Robot-local correction ACK guards; no devices or subprocesses."""
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/twinpulse_robot_safety'))
from observed_runtime import RobotObservedFactory
from mission_runtime import run_mission
from twinpulse_core.mission_correction_contract import correction_reply
from packages.twinpulse_core.tests import test_mission_correction_contract as fixtures


class IdleCorrectionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CorrectionContractTests.setUpClass()

    def factory(self):
        fixture=fixtures.CorrectionContractTests();scope=fixture.scope();proposal=fixture.proposal()
        clock=[11.];emitted=[]
        # Only instantiate the method's guarded state, not a sensor factory.
        factory=RobotObservedFactory.__new__(RobotObservedFactory)
        factory.scope=scope;factory.proposal=proposal;factory.proposal_sent=True;factory.reply=None
        factory.correction_lock=threading.RLock();factory.clock=lambda:clock[0];factory.output=emitted.append
        factory.mission=SimpleNamespace(cancelled=threading.Event(),stage='ALIGN',proposed=(0.,0.),
            mission=SimpleNamespace(status='RUNNING'))
        binding={'schema':'mission-photo-binding-1.0','goal':{**scope['goal'],'room_revision':'e'*64},'applied_revision':'f'*64}
        return factory,correction_reply(proposal,scope,binding),clock,emitted

    def test_owned_idle_reply_consumed_once_without_changing_scope_or_budget(self):
        factory,reply,clock,emitted=self.factory();original=factory.scope.copy()
        factory.accept_correction(reply)
        self.assertEqual(factory.reply,reply);self.assertEqual(factory.scope,original);self.assertEqual(clock,[11.])
        self.assertEqual(len(emitted),1);self.assertEqual(emitted[0]['state'],'ADAPTIVE_CORRECTION_ACCEPTED')
        with self.assertRaisesRegex(ValueError,'CORRECTION_ACK_REQUIRES_OWNED_IDLE'):factory.accept_correction(reply)
        self.assertEqual(len(emitted),1)

    def test_stop_motion_wrong_phase_unsent_and_expired_never_ack(self):
        cases=('cancelled','moving','phase','terminal','unsent','expired','wrong_nonce')
        for case in cases:
            with self.subTest(case=case):
                factory,reply,clock,emitted=self.factory()
                if case=='cancelled':factory.mission.cancelled.set()
                elif case=='moving':factory.mission.proposed=(.03,0.)
                elif case=='phase':factory.mission.stage='NAVIGATE'
                elif case=='terminal':factory.mission.mission.status='ARRIVED'
                elif case=='unsent':factory.proposal_sent=False
                elif case=='expired':clock[0]=12.
                else:reply={**reply,'nonce':'0'*24}
                with self.assertRaises(ValueError):factory.accept_correction(reply)
                self.assertIsNone(factory.reply);self.assertFalse(emitted)

    def test_output_failure_does_not_accept_reply(self):
        factory,reply,_,_=self.factory()
        factory.output=lambda _:(_ for _ in ()).throw(OSError('TEST_PIPE_FAILURE'))
        with self.assertRaises(OSError):factory.accept_correction(reply)
        self.assertIsNone(factory.reply)

    def test_real_input_gate_expires_despite_valid_idle_correction_ack(self):
        guard,reply,clock,emitted=self.factory();guard.mission.mission.end=56.
        events=[];sent_watch=[False];sent_reply=[False];challenge=[None]
        class Incoming:
            def receive(self):
                if not sent_watch[0] and challenge[0]:
                    sent_watch[0]=True
                    return {'sequence':1,'action':'watch','age_ms':0,'challenge':challenge[0]}
                if clock[0]>=11.2 and not sent_reply[0]:
                    sent_reply[0]=True;return reply
                return None
        class Link:
            rows=[];halted=False
            def spin(self,dt):clock[0]+=dt
            def fresh(self):pass
            def halt(self):self.halted=True
            def navigation_snapshot(self):return {}
            def navigation_step(self,mission,binding,created,*,before_publish):
                before_publish()
                return {'linear_m_s':0.,'angular_rad_s':0.}
        class Factory:
            def __call__(self,started):return guard.mission
            def accept_correction(self,value):guard.accept_correction(value)
        def output(value):challenge[0]=value['challenge']
        link=Link()
        request={'mission_id':'b'*32,'request_sha256':'c'*64,'expires_s':90.,'binding':None}
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):
            run_mission(link,Incoming(),output,request,record=lambda kind,**data:events.append((kind,data)),
                consume=lambda:None,clock=lambda:clock[0],mission_factory=Factory())
        self.assertTrue(sent_reply[0]);self.assertIsNotNone(guard.reply);self.assertEqual(len(emitted),1)
        self.assertTrue(link.halted);self.assertLess(clock[0],11.3);self.assertEqual(guard.mission.mission.end,56.)


if __name__=='__main__':unittest.main()
