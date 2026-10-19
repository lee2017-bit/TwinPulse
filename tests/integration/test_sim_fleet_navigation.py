# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure/SIM contract tests, not real Isaac or hardware acceptance."""
from copy import deepcopy
import math
import unittest
from tests.integration import test_robot_fleet as fixture
from twinpulse_app.robot_fleet import parse_robot_command
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.sim_fleet_navigation import approach_plan,next_leg,checked_navigation_report
from scripts.twinpulse_fleet_runtime import integrate_motion
from scripts.twinpulse_fleet_runtime import FleetRuntime
from concurrent.futures import Future


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.target=dict(id='bed1',kind='bed',label='bed bed1',bounds=[1.,3.,2.,4.5])
    def test_destination_not_furniture_edit_or_scene_generation(self):
        for text in ('Go to the nearest bed','Alpha robot, move to the nearest chair','가까운 침대로 이동해줘'):
            self.assertEqual(parse_robot_command(text)['action'],'navigate')
        for text in ('Move the chair to the left','Create a room with a bed and chair'):
            self.assertIsNone(parse_robot_command(text))
        self.assertEqual(parse_robot_command('Alpha stop'),{'action':'stop'})
    def test_actual_path_and_same_collision_integrator_arrive_outside_bed(self):
        pose=[2.5,1.,0.];obstacles=[self.target['bounds']]
        plan=approach_plan(pose,'bed',[self.target],[0,0,5,5],obstacles)
        self.assertEqual(plan['target_id'],'bed1');self.assertFalse(plan['physical_authority'])
        index=0;elapsed=0.
        for _ in range(1200):
            direction,remaining,index=next_leg(pose,plan['waypoints'],index)
            if direction is None:break
            pose,_,reason,_=integrate_motion(pose,direction,.1,obstacles,remaining)
            self.assertIsNone(reason);elapsed+=.1
        self.assertLess(elapsed,120.)
        self.assertLess(math.dist(pose[:2],plan['goal_xy']),.016)
        self.assertGreaterEqual(math.hypot(max(1-pose[0],0,pose[0]-2),max(3-pose[1],0,pose[1]-4.5)),.25)
    def test_no_fallback_to_farther_bed_when_nearest_enclosed(self):
        far=dict(id='bed2',kind='bed',label='far',bounds=[4,4,4.4,4.4])
        with self.assertRaisesRegex(ValueError,'NO_REACHABLE'):
            approach_plan([2.5,1.,0.],'bed',[self.target,far],[0,0,5,5],[[.5,2.5,2.5,4.9]])
    def test_missing_tied_and_invalid_geometry_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError,'MISSING'):approach_plan([0,0,0],'chair',[self.target],[0,0,5,5],[])
        twin=deepcopy(self.target);twin['id']='another'
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):approach_plan([2.5,1,0],'bed',[self.target,twin],[0,0,5,5],[])
        with self.assertRaisesRegex(ValueError,'SCENE_INVALID'):approach_plan([math.nan,0,0],'bed',[self.target],[0,0,5,5],[])
    def test_report_is_bounded_and_task_bound(self):
        value=dict(request_id='r',state='PLANNING',target_kind='bed',reason=None)
        self.assertEqual(checked_navigation_report(value,'r'),value)
        for row in ({**value,'request_id':'old'},{**value,'waypoints':{}},{**value,'remaining_m':math.nan},{**value,'physical_authority':True}):
            self.assertIsNone(checked_navigation_report(row,'r'))


class FleetNavigationTests(unittest.TestCase):
    setUp=fixture.FleetTests.setUp
    tearDown=fixture.FleetTests.tearDown
    send=fixture.FleetTests.send
    register=fixture.FleetTests.register
    report=fixture.FleetTests.report
    connected=fixture.FleetTests.connected
    def test_destination_command_has_identity_and_stop_cancels_without_replay(self):
        identity=self.connected();row=self.fleet.robots[identity]
        state=self.send('command',identity,dict(text='Go to the nearest bed'))
        command=state['robots'][0]['command'];self.assertEqual(command['state'],'ACCEPTED')
        self.assertEqual(row['_task']['task_id'],command['request_id']);self.assertEqual(row['_task']['kind'],'navigate')
        self.send('stop',identity)
        self.assertEqual(row['command']['state'],'CANCELLED');self.assertIsNone(row['_task'])
        self.report(identity);self.assertIsNone(row['_task'])


class RuntimeNavigationTests(unittest.TestCase):
    def test_environment_revision_rejects_old_worker_result(self):
        runtime=FleetRuntime();future=Future()
        robot=dict(pose=[0,0,0],navigation=dict(request_id='old',state='PLANNING'),navigation_geometry_epoch=0,navigation_future=future)
        runtime.navigation_geometry_epoch=1
        self.assertEqual(runtime._navigate(robot,dict(task_id='old',target_kind='bed'),None,'r')[2],'NAVIGATION_SCENE_CHANGED')
        future.set_result(dict(waypoints=[[1,0]]))
        self.assertEqual(robot['navigation']['state'],'FAILED')


if __name__=='__main__':unittest.main()
