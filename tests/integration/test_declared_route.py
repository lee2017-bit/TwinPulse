# SPDX-License-Identifier: Apache-2.0
import math
from pathlib import Path
import time
import unittest

from tests.integration import test_r5_product_api  # noqa: F401  (adds package source paths)

from twinpulse_core.declared_route import plan_survey, compile_moves, move_text, integrate
from twinpulse_app.robot_fleet import parse_robot_command


def room():
    # 4 x 3 m room with a sofa-sized box; no grid mask (plain model geometry).
    return dict(bounds=[0.,0.,4.,3.],obstacles=[[2.6,2.2,3.9,2.9]],targets=[])


class DeclaredRouteTests(unittest.TestCase):
    def test_survey_visits_waypoints_and_closes_at_the_declared_start(self):
        start=[.6,.6,0.]
        plan=plan_survey(start,room(),kind='physical',budget_m=8.)
        self.assertGreaterEqual(len(plan['waypoints']),2)
        self.assertEqual(plan['polyline'][-1][:2],start[:2])
        self.assertEqual(plan['scope'],'DECLARED_START_MODEL_PLAN_NOT_LOCALIZED')
        self.assertLessEqual(plan['length_m'],8.+1e-9)

    def test_compiled_moves_reproduce_route_and_restore_heading(self):
        start=[.6,.6,.3]
        plan=plan_survey(start,room(),kind='physical',budget_m=8.)
        steps=compile_moves(start,plan['polyline'],final_yaw=start[2])
        end=integrate(start,steps)
        self.assertLess(math.dist(end[:2],start[:2]),1e-6)
        self.assertLess(abs(math.remainder(end[2]-start[2],math.tau)),1e-6)
        self.assertTrue(all(s['amount']<=1.+1e-9 for s in steps if s['direction']=='forward'))

    def test_step_text_round_trips_through_the_existing_finite_parser(self):
        steps=[dict(direction='forward',amount=.734),dict(direction='left',amount=1.2345),dict(direction='right',amount=.05)]
        for s in steps:
            parsed=parse_robot_command(move_text(s))
            self.assertEqual(parsed['action'],'task');self.assertEqual(parsed['direction'],s['direction'])
            self.assertAlmostEqual(parsed['amount'],s['amount'],delta=.001)

    def test_no_reachable_waypoint_is_an_error_not_an_empty_route(self):
        boxed=dict(bounds=[0.,0.,.5,.5],obstacles=[],targets=[])
        with self.assertRaisesRegex(ValueError,'DECLARED_ROUTE_NO_REACHABLE_WAYPOINT'):
            plan_survey([.25,.25,0.],boxed)


class FakeFleet:
    """Finite commands complete (or not) per script; Stop flips the robot to OPERATOR_STOP."""
    def __init__(self,outcomes):
        self.outcomes=list(outcomes);self.sent=[]
        self.row=dict(robot_id='r'*32,kind='sim',control_state='READY',reason=None,connection_epoch='c',motion_epoch='m0',
            pose=dict(position_m=[.6,.6,0.]),command=None,lidar_state='OFF')
        self.navigation_scene=dict(binding=('e','s','rev'),geometry=room(),observed_cells=None)
    def snapshot(self):return dict(robots=[dict(self.row)])
    def action(self,body,owner):
        self.sent.append(body)
        if body['action']=='stop':self.row.update(reason='OPERATOR_STOP');return
        outcome=self.outcomes.pop(0) if self.outcomes else 'COMPLETED'
        if outcome=='HANG':self.row.update(command=dict(request_id=body['request_id'],state='RUNNING'));return
        self.row.update(command=dict(request_id=body['request_id'],state=outcome,reason='X'),
            reason='TASK_COMPLETED' if outcome=='COMPLETED' else 'OPERATOR_STOP',motion_epoch=body['request_id'])


def run(fleet,tmp,**kw):
    from twinpulse_app.declared_route_runner import DeclaredRouteRunner
    results=[];clock=[0.]
    def sleep(s):clock[0]+=s
    runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:clock[0],sleep=sleep,poll_s=1.,on_result=results.append,**kw)
    runner.start(fleet.row['robot_id'],'owner')
    for _ in range(2000):
        if results:break
        time.sleep(.001)
    return runner,results[0]


class DeclaredRouteRunnerTests(unittest.TestCase):
    def test_all_steps_sent_as_ordinary_commands_in_order(self):
        import tempfile
        fleet=FakeFleet([])
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
            self.assertEqual(result['state'],'COMPLETED')
            self.assertEqual([b['payload']['text'] for b in fleet.sent],[s['text'] for s in result['plan']['steps']])
            self.assertTrue(all(b['action']=='command' for b in fleet.sent))
            self.assertTrue(list(Path(tmp,'declared-routes').glob('*.json')))

    def test_failed_step_halts_and_no_later_step_is_sent(self):
        import tempfile
        fleet=FakeFleet(['COMPLETED','FAILED'])
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'STOPPED');self.assertEqual(result['completed_steps'],1)
        self.assertEqual(len(fleet.sent),2)

    def test_timeout_sends_stop_and_fails(self):
        import tempfile
        fleet=FakeFleet(['HANG'])
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['reason'],'STEP_TIMEOUT');self.assertEqual(fleet.sent[-1]['action'],'stop')

    def test_external_stop_between_steps_halts(self):
        import tempfile
        fleet=FakeFleet(['COMPLETED'])
        original=fleet.action
        def action(body,owner):
            original(body,owner)
            if len(fleet.sent)==1:fleet.row['reason']='OPERATOR_STOP'  # operator pressed Stop after step 1
        fleet.action=action
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'STOPPED');self.assertEqual(len(fleet.sent),1)

    def test_physical_requires_declared_pose_on_current_scene(self):
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        from twinpulse_app.command_broker import BrokerError
        fleet=FakeFleet([]);fleet.row.update(kind='physical',display_pose=dict(position_m=[.6,.6,0.],scene_revision='old'))
        with self.assertRaisesRegex(BrokerError,'Set the robot position'):
            DeclaredRouteRunner(fleet,'.').plan(fleet.row['robot_id'])
        fleet.row['display_pose']['scene_revision']='rev'
        plan=DeclaredRouteRunner(fleet,'.').plan(fleet.row['robot_id'])
        self.assertEqual(plan['start_basis'],'operator_declared_display_pose')


if __name__=='__main__':unittest.main()
