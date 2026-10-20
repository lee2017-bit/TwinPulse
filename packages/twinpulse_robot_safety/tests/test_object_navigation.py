# SPDX-License-Identifier: Apache-2.0
"""Device-free route/control contract tests. Never physical trial evidence."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.physical_object_navigation import transform_pose,route_from_plan,checked_route,route_step
from fleet_control import RobotControl


def tracking(pose=None):return dict(status='ESTIMATED',epoch='native-epoch',pose=pose or [0.,0.,0.],sample_s=1.)
def route():
    return route_from_plan(dict(waypoints=[[1.,0.]],goal_xy=[1.,0.],target_kind='bed',target_id='bed1',target_label='bed'),
        dict(origin=[0.,0.,0.],world=[0.,0.,0.]),tracking(),'context','visual')


class ContractTests(unittest.TestCase):
    def test_anchor_translation_rotation_and_inverse(self):
        from math import pi
        self.assertEqual(transform_pose([2.,1.,.3],[1.,1.,0.],[10.,20.,pi/2])[:2],[10.,21.])
        p=[2.,3.,.4];o=[1.,1.,.6];w=[10.,20.,.8]
        result=transform_pose(transform_pose(p,o,w),w,o)
        for a,b in zip(p,result):self.assertAlmostEqual(a,b)
    def test_route_is_estimated_bounded_and_follows_current_native_pose(self):
        r=route();self.assertIn('UNQUALIFIED',r['accuracy'])
        self.assertEqual(route_step(r,tracking(),0,1.),('forward',0,1.))
        self.assertEqual(route_step(r,tracking([.98,0.,0.]),0,1.),(None,1,0))
        self.assertEqual(route_step(r,tracking([0.,0.,1.]),0,1.)[0],'right')
    def test_changed_epoch_stale_pose_changed_start_and_oversized_routes_reject(self):
        r=route()
        for t,now in [({**tracking(),'epoch':'new'},1.),(tracking(),1.61),({**tracking(),'pose':None},1.)]:
            with self.assertRaises(ValueError):checked_route(r,t,now)
        with self.assertRaisesRegex(ValueError,'START_CHANGED'):checked_route(r,tracking([.1,0.,0.]),1.)
        for change in ({'waypoints':[[6.,0.]]},{'extra':'code'},{'sample_s':float('nan')}):
            with self.assertRaises(ValueError):checked_route({**r,**change},tracking(),1.)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.calls=[]
        self.owner=RobotControl(dict(project_id='project'),'.',lambda *e:self.events.append(e),SimpleNamespace(),clock=lambda:1.)
        o=self.owner;o.field_mode=True;o.tracker=SimpleNamespace(snapshot=tracking)
        o._movement_ready=lambda:None;o._safety=lambda:None
        o.link=SimpleNamespace(enabled=False,sensor=SimpleNamespace(torque=False),
            enable=lambda:self.calls.append('enable'),release=lambda:self.calls.append('release'))
        o.guard=SimpleNamespace(require_body=False,reset=lambda:self.calls.append('guard_reset'))
        # Native guard callable and reset remain real control-boundary calls,
        # but hardware effects are deliberately mocked in this supplementary test.
        class Guard:
            require_body=False
            def __call__(_self,*args):self.calls.append('native_guard')
            def reset(_self):self.calls.append('guard_reset')
        o.guard=Guard()
    def command(self,action,payload):
        o=self.owner
        return dict(action=action,payload=dict(payload,challenge=o.gate.challenge(),motion_generation=o.gate.generation,source_age_ms=0),
                    sequence=o.gate.sequence+1,request_id='request',motion_epoch='motion',request_twin_context={'context_id':'context','project_id':'project'})
    def start(self):
        self.owner._command(self.command('task',dict(kind='estimated_object_route',route=route(),text='Go to bed')))
    def test_no_output_or_enable_before_fresh_arm_and_post_arm_watches(self):
        self.start();o=self.owner
        self.assertIsNone(o.direction);self.assertNotIn('enable',self.calls)
        o._command(self.command('watch',{}));self.assertEqual(self.calls[:2],['native_guard','enable'])
        self.assertIsNone(o.direction)
        o._command(self.command('watch',{}));self.assertEqual(o.direction,'forward')
        self.assertTrue(o.guard.require_body)
    def test_direction_change_stops_before_rearm_and_old_epoch_cannot_continue(self):
        self.test_no_output_or_enable_before_fresh_arm_and_post_arm_watches();o=self.owner
        o.tracker=SimpleNamespace(snapshot=lambda:tracking([0.,0.,1.]))
        o._route_tick();self.assertIn('release',self.calls);self.assertIsNone(o.direction)
        self.assertEqual(o.task['status'],'WAITING_ROUTE_ARM_WATCH')
        o.tracker=SimpleNamespace(snapshot=lambda:{**tracking(),'epoch':'new'})
        with self.assertRaises(ValueError):o._route_tick()
    def test_stop_discards_route_and_preserves_command_receipt(self):
        self.start();self.owner._command(self.command('stop',{}))
        self.assertIsNone(self.owner.task);self.assertIsNone(self.owner.direction)
        self.assertEqual(self.owner.state['command']['state'],'CANCELLED')
    def test_arrival_is_estimate_not_verified_physical_furniture_arrival(self):
        self.start();o=self.owner;o.tracker=SimpleNamespace(snapshot=lambda:tracking([1.,0.,0.]))
        o._route_tick();self.assertIsNone(o.task)
        self.assertEqual(o.state['command']['state'],'ESTIMATE_REACHED')
    def test_missing_context_or_tracking_is_not_silently_simulated(self):
        c=self.command('task',dict(kind='estimated_object_route',route=route(),text='Go to bed'))
        c['request_twin_context']['context_id']='old'
        with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):self.owner._command(c)
        self.assertFalse(self.calls)


if __name__=='__main__':unittest.main()
