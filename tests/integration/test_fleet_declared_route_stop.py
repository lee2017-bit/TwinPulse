# SPDX-License-Identifier: Apache-2.0
"""A Stop is never erased by starting a declared route (2026-10-27 review).

Uses the real RobotFleet, not the FakeFleet of test_declared_route: the bug lived
between DeclaredRouteRunner.start() and the fleet's Stop/epoch handling.
"""
from pathlib import Path
import tempfile
import time
import unittest

from tests.integration import test_r5_product_api  # noqa: F401  (adds package source paths)
from tests.integration.test_robot_fleet import Broker
from tests.integration.test_declared_route import room
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.declared_route_runner import DeclaredRouteRunner
from twinpulse_app.robot_fleet import RobotFleet


class RouteStopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.now=100.;self.counter=0
        self.fleet=RobotFleet(Broker(),Path(self.temp.name),clock=lambda:self.now,wall=lambda:self.now)
        self.robot=self.send('register_sim',payload=dict(label='Alpha',position_m=[1,1,0]))['focused_robot_id']
        self.send('connect',self.robot);self.report();self.send('prepare',self.robot)
        self.fleet.navigation_scene=dict(binding=('engine','stage','revision'),geometry=room(),produced_at=self.now,observed_cells=None)
        clock=[0.]
        def sleep(s):clock[0]+=s;time.sleep(.002)
        self.runner=DeclaredRouteRunner(self.fleet,self.temp.name,clock=lambda:clock[0],sleep=sleep,poll_s=1.)

    def tearDown(self):
        self.runner.cancel();time.sleep(.05);self.fleet.close();self.temp.cleanup()

    def send(self,action,robot=None,payload=None):
        self.counter+=1
        return self.fleet.action(dict(action=action,request_id='request_'+str(self.counter),robot_id=robot,
            connection_epoch=None,motion_epoch=None,payload=payload or {}),'owner')

    def report(self):
        row=self.fleet.robots[self.robot]
        value=dict(robot_id=self.robot,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],
            sequence=row['telemetry_sequence']+1,position_m=[1,1,0],
            runtime_startup=dict(model_authored=True,render_observed=True,snapshot_capture_pending=False,post_author_updates=2,ready=True))
        self.fleet.engine_exchange('engine','stage',dict(engine_session_id='engine',stage_epoch='stage',
            report=dict(applied_revision='revision',robots=[value])))

    def finite_command(self,wait_s=1.):
        until=time.monotonic()+wait_s
        while time.monotonic()<until:
            command=self.fleet.robots[self.robot].get('command') or {}
            if command.get('kind')=='finite':return command
            time.sleep(.002)
        return None

    def assert_refused_and_still(self,plan):
        with self.assertRaises(BrokerError) as caught:self.runner.start(plan,'owner')
        self.assertEqual(caught.exception.code,'declared_route_stopped')
        self.assertIsNone(self.finite_command(.3),'a route step reached the robot after the Stop')
        self.assertIsNone(self.fleet.robots[self.robot].get('_task'))
        self.assertFalse(self.runner.active())

    def test_route_without_stop_still_sends_its_first_step(self):
        plan=self.runner.plan(self.robot)
        self.runner.start(plan,'owner')
        self.assertIsNotNone(self.finite_command())

    def test_stop_before_asking_for_the_route_does_not_block_the_new_plan(self):
        self.send('stop_all')
        plan=self.runner.plan(self.robot)
        self.runner.start(plan,'owner')
        self.assertIsNotNone(self.finite_command())

    def test_stop_after_the_route_card_refuses_run(self):
        plan=self.runner.plan(self.robot)
        self.send('stop_all')  # robot card Stop all while the card waits
        self.assertEqual(self.fleet.robots[self.robot]['control_state'],'PAUSED')  # the state start() accepts
        self.assert_refused_and_still(plan)

    def test_stop_while_run_is_being_admitted_refuses_run(self):
        plan=self.runner.plan(self.robot)
        original=self.runner._start_pose;fired=[]
        def start_pose(row,scene):  # Stop lands inside start(), after its readiness reads
            if not fired:fired.append(1);self.send('stop_all')
            return original(row,scene)
        self.runner._start_pose=start_pose
        self.assert_refused_and_still(plan)
        self.assertTrue(fired)

    def test_stop_during_planning_refuses_run(self):
        original=self.runner.readiness;fired=[]
        def readiness(robot_id):
            value=original(robot_id)
            if not fired:fired.append(1);self.send('stop_all')
            return value
        self.runner.readiness=readiness
        plan=self.runner.plan(self.robot)
        self.assert_refused_and_still(plan)

    def test_chat_stop_after_the_route_card_refuses_run(self):
        plan=self.runner.plan(self.robot)
        self.runner.cancel()  # what ConversationService does for a chat "stop" before the fleet Stop
        self.assert_refused_and_still(plan)

    def test_stop_right_after_admission_cancels_before_any_step(self):
        plan=self.runner.plan(self.robot)
        original=self.runner._save;fired=[]
        def save():  # start() saves the record right after admitting the run (cancel flag cleared)
            original()
            if not fired:fired.append(1);self.send('stop_all')
        self.runner._save=save
        self.runner.start(plan,'owner')
        until=time.monotonic()+2.
        while self.runner.active() and time.monotonic()<until:time.sleep(.002)
        self.assertFalse(self.runner.active())
        self.assertEqual(self.runner.current['state'],'CANCELLED')
        self.assertFalse(self.runner.current.get('sent'))
        self.assertIsNone(self.finite_command(.1))

    def test_stop_between_the_cancel_check_and_the_send_is_rejected_by_epoch(self):
        plan=self.runner.plan(self.robot)
        real=self.fleet.action;fired=[];errors=[]
        def action(body,owner,**kw):
            if body['action']=='command' and body['robot_id']==self.robot and body['motion_epoch'] is not None and not fired:
                fired.append(1);real(dict(action='stop_all',request_id='s'*32,robot_id=None,connection_epoch=None,motion_epoch=None,payload={}),'owner')
            try:return real(body,owner,**kw)
            except BrokerError as exc:errors.append(exc.code);raise
        self.fleet.action=action
        self.runner.start(plan,'owner')
        until=time.monotonic()+2.
        while self.runner.active() and time.monotonic()<until:time.sleep(.002)
        self.assertIn('fleet_motion_epoch_changed',errors)
        self.assertIsNone(self.fleet.robots[self.robot].get('_task'))
        self.assertFalse(self.runner.current.get('sent'))


if __name__=='__main__':unittest.main()
