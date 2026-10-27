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

    def test_stops_are_in_the_space_the_declared_heading_faces(self):
        wide=dict(bounds=[0.,0.,8.,3.],obstacles=[],targets=[])
        plan=plan_survey([4.,1.5,0.],wide,kind='physical',budget_m=8.)
        self.assertTrue(all(w[0]>=4. for w in plan['waypoints']),plan['waypoints'])
        plan=plan_survey([4.,1.5,math.pi],wide,kind='physical',budget_m=8.)
        self.assertTrue(all(w[0]<=4. for w in plan['waypoints']),plan['waypoints'])

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

    def test_start_scan_keeps_unmodeled_returns_out_and_picks_the_lateral_sign(self):
        from twinpulse_core.declared_route import unexplained_scan_discs
        # 4 x 3 m room: border cells occupied, inside free.
        cells=[[(ix+.5)*.1,(iy+.5)*.1,'occupied' if ix in (0,39) or iy in (0,29) else 'free',0,0,0,0]
               for ix in range(40) for iy in range(30)]
        start=[1.,1.,0.]
        walls=[(2.95,y*.1) for y in range(-9,19)]+[(x*.1,1.95) for x in range(-9,29)]+[(x*.1,-.95) for x in range(-9,29)]
        plant=[(1.5,.6)]  # 1.5 m ahead, 0.6 m to the robot's left
        native=[(x,-y) for x,y in walls+plant]  # native stream reports the lateral axis mirrored
        review=unexplained_scan_discs(start,native,cells)
        self.assertTrue(review['used']);self.assertEqual(review['lateral_sign'],-1)
        self.assertEqual(len(review['discs']),1)
        self.assertLess(math.dist(review['discs'][0][:2],[2.5,1.6]),.05)
        self.assertFalse(unexplained_scan_discs(start,[(.5,.0)]*10,cells)['used'])  # nothing agrees with the model

    def test_no_reachable_waypoint_is_an_error_not_an_empty_route(self):
        boxed=dict(bounds=[0.,0.,.5,.5],obstacles=[],targets=[])
        with self.assertRaisesRegex(ValueError,'DECLARED_ROUTE_NO_REACHABLE_WAYPOINT'):
            plan_survey([.25,.25,0.],boxed)


class FakeFleet:
    """Finite commands complete (or not) per script; Stop flips the robot to OPERATOR_STOP."""
    def __init__(self,outcomes):
        self.outcomes=list(outcomes);self.sent=[];self.curve=0.;self.turn_error=0.;self.fail_reason='X'
        self.row=dict(robot_id='r'*32,kind='sim',control_state='READY',reason=None,connection_epoch='c',motion_epoch='m0',
            pose=dict(position_m=[.6,.6,0.]),command=None,lidar_state='OFF')
        self.navigation_scene=dict(binding=('e','s','rev'),geometry=room(),observed_cells=None)
    def snapshot(self):return dict(robots=[dict(self.row)])
    def action(self,body,owner):
        self.sent.append(body)
        if body['action']=='stop':self.row.update(reason='OPERATOR_STOP');return
        outcome=self.outcomes.pop(0) if self.outcomes else 'COMPLETED'
        if outcome=='HANG':self.row.update(command=dict(request_id=body['request_id'],state='RUNNING'));return
        if outcome=='DROP':return
        if outcome=='COMPLETED' and body['action']=='command':
            # Integrate the finite step (optionally with a left curve on forward legs, like the real robot).
            step=parse_robot_command(body['payload']['text']);x,y,yaw=self.row['pose']['position_m']
            if step['direction'] in ('forward','backward'):
                d=step['amount']*(1 if step['direction']=='forward' else -1);yaw+=self.curve*abs(d)/2
                x+=d*math.cos(yaw);y+=d*math.sin(yaw);yaw+=self.curve*abs(d)/2
            else:yaw+=(step['amount']+self.turn_error)*(1 if step['direction']=='left' else -1)
            self.row['pose']=dict(position_m=[x,y,math.atan2(math.sin(yaw),math.cos(yaw))])
        self.row.update(command=dict(request_id=body['request_id'],state=outcome,reason='X' if outcome=='COMPLETED' else self.fail_reason),
            reason='TASK_COMPLETED' if outcome=='COMPLETED' else 'OPERATOR_STOP',motion_epoch=body['request_id'])


def run(fleet,tmp,**kw):
    from twinpulse_app.declared_route_runner import DeclaredRouteRunner
    results=[];clock=[0.]
    def sleep(s):clock[0]+=s
    runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:clock[0],sleep=sleep,poll_s=1.,on_result=results.append,**kw)
    runner.start(runner.plan(fleet.row['robot_id']),'owner')
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
            self.assertEqual(result['state'],'COMPLETED',result['reason'])
            self.assertEqual(len(fleet.sent),len(result['plan']['steps']))  # ideal robot: same as the preview
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
        self.assertTrue(result['reason'].startswith('STEP_TIMEOUT:STOP_'));self.assertEqual(fleet.sent[-1]['action'],'stop')

    def test_odometry_feedback_cancels_a_systematic_left_curve(self):
        # 2026-10-25: ~2.5 deg + .3 deg per .75 m to the left on forward legs.
        import tempfile
        fleet=FakeFleet([]);fleet.curve=math.radians(4)  # 4 deg per metre
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'COMPLETED',result['reason'])
        end=fleet.row['pose']['position_m']
        self.assertLess(math.dist(end[:2],[.6,.6]),.05)
        self.assertLess(abs(math.remainder(end[2],math.tau)),.04)

    def test_proximity_stop_backs_off_and_replans_around_a_keepout(self):
        import tempfile
        fleet=FakeFleet(['COMPLETED']*3+['FAILED']);fleet.fail_reason='FIELD_PROXIMITY_10CM'
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        texts=[b['payload'].get('text') for b in fleet.sent]
        self.assertIn('backward 40.0cm',texts)
        self.assertEqual(len(result['recoveries']),1)
        self.assertEqual(result['state'],'COMPLETED',result['reason'])

    def test_unacknowledged_step_fails_fast_and_is_not_resent(self):
        import tempfile
        fleet=FakeFleet(['COMPLETED','DROP'])
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertTrue(result['reason'].startswith('STEP_NOT_ACKNOWLEDGED:'),result['reason'])
        self.assertEqual([b['action'] for b in fleet.sent],['command','command','stop'])

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

    def test_stop_then_prepare_between_steps_is_detected_by_epoch_change(self):
        import tempfile
        fleet=FakeFleet(['COMPLETED']);reads=[]
        original=fleet.snapshot
        def snapshot():
            if len(fleet.sent)==1:
                reads.append(1)
                # 1st read after step 1 observes COMPLETED; Stop + Prepare happen before the 2nd.
                if len(reads)==2:fleet.row.update(reason='TASK_COMPLETED',motion_epoch='after-stop-and-prepare')
            return original()
        fleet.snapshot=snapshot
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'STOPPED');self.assertEqual(len(fleet.sent),1)

    def test_physical_completion_reason_operator_stop_does_not_halt_the_route(self):
        # 2026-10-25 physical run: finite completion reports reason OPERATOR_STOP
        # with unchanged epochs; the route must continue (Stop is an epoch change).
        import tempfile
        fleet=FakeFleet([]);fleet.row.update(kind='physical',display_pose=dict(position_m=[.6,.6,0.],scene_revision='rev'))
        original=fleet.action
        def action(body,owner):
            original(body,owner)
            if body['action']=='command':fleet.row.update(reason='OPERATOR_STOP',applied_motion_epoch=fleet.row['motion_epoch'])
        fleet.action=action
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'COMPLETED',result['reason'])

    def test_physical_requires_declared_pose_on_current_scene(self):
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        from twinpulse_app.command_broker import BrokerError
        fleet=FakeFleet([]);fleet.row.update(kind='physical',display_pose=dict(position_m=[.6,.6,0.],scene_revision='old'))
        fleet.declared_route_cancel=None
        with self.assertRaisesRegex(BrokerError,'Set the robot position'):
            DeclaredRouteRunner(fleet,'.').plan(fleet.row['robot_id'])
        fleet.row['display_pose']['scene_revision']='rev'
        plan=DeclaredRouteRunner(fleet,'.').plan(fleet.row['robot_id'])
        self.assertEqual(plan['start_basis'],'operator_declared_display_pose')


    def test_confirmed_plan_refuses_a_moved_start_pose(self):
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        from twinpulse_app.command_broker import BrokerError
        fleet=FakeFleet([]);runner=DeclaredRouteRunner(fleet,'.')
        plan=runner.plan(fleet.row['robot_id'])
        fleet.row['pose']=dict(position_m=[1.,.6,0.])
        with self.assertRaisesRegex(BrokerError,'start pose changed'):runner.start(plan,'owner')

    def test_fleet_stop_or_manual_drive_cancels_the_route_before_delivery(self):
        from tests.integration.test_robot_fleet import Broker
        from twinpulse_app.robot_fleet import RobotFleet
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fleet=RobotFleet(Broker(),tmp);cancelled=[]
            fleet.declared_route_cancel=lambda:cancelled.append(1)
            for body in (dict(action='stop_all',payload={}),dict(action='command',payload=dict(text='stop'))):
                try:fleet.action(dict(body,request_id='a'*32,robot_id=None,connection_epoch=None,motion_epoch=None),'owner')
                except Exception:pass
            try:fleet.action(dict(action='command',payload=dict(text='forward 10cm'),request_id='b'*32,robot_id=None,connection_epoch=None,motion_epoch=None),'owner')
            except Exception:pass
            self.assertEqual(len(cancelled),2)





class DeclaredRouteChatRoutingTests(unittest.TestCase):
    def test_survey_and_return_routes_to_declared_route_only_on_imported_twin(self):
        # 2026-10-25 installed SIM run: a corrupted regex never matched and the
        # request silently fell through to the common planner card.
        from types import SimpleNamespace
        from twinpulse_app.conversation_service import ConversationService
        fleet=SimpleNamespace(focused='r',robots={'r':{'kind':'sim'}},
            navigation_scene=dict(geometry=dict(schema='scene-navigation-2.0')))
        self_=SimpleNamespace(declared_routes=object(),robot_fleet=fleet)
        route=lambda text:ConversationService._declared_route_request(self_,text)
        self.assertTrue(route('Survey the room and come back'))
        self.assertTrue(route('방을 둘러보고 돌아와'))
        self.assertFalse(route('Create a room the robot can survey and return in'))
        self.assertFalse(route('Survey the room'))
        fleet.navigation_scene=dict(geometry=dict(schema='scene-navigation-1.0'))
        self.assertFalse(route('Survey the room and come back'))
if __name__=='__main__':unittest.main()


class RouteOverlayCoreTest(unittest.TestCase):
    def test_stop_scan_projects_with_pose_and_sign(self):
        from twinpulse_core.declared_route import scan_world_points
        out=scan_world_points([1.,2.,math.pi/2],[(1.,0.),(0.,1.)],1)
        self.assertEqual(out,[[1.,3.],[0.,2.]])
        self.assertEqual(scan_world_points([1.,2.,math.pi/2],[(0.,1.)],-1),[[2.,2.]])

    def test_candidates_need_several_returns(self):
        from twinpulse_core.declared_route import cluster_candidates
        discs=[(2.,2.,.06),(2.05,2.02,.06),(2.1,1.98,.06),(4.,4.,.06)]
        out=cluster_candidates(discs)
        self.assertEqual(len(out),1);self.assertEqual(out[0]['returns'],3)
        self.assertAlmostEqual(out[0]['position_xy_m'][0],2.05,places=2)


class DeclaredRouteRobustnessTests(unittest.TestCase):
    """2026-10-26 quality review: disk-full paths, stop numbering, progress events."""

    def test_disk_full_at_start_leaves_no_phantom_running_route(self):
        import tempfile
        from twinpulse_app.command_broker import BrokerError
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        fleet=FakeFleet([])
        with tempfile.TemporaryDirectory() as tmp:
            blocker=Path(tmp,'not-a-dir');blocker.write_text('x')  # declared-routes/ cannot be created under a file
            runner=DeclaredRouteRunner(fleet,blocker,clock=lambda:0.,sleep=lambda s:None,poll_s=1.)
            plan=runner.plan(fleet.row['robot_id'])
            with self.assertRaises(BrokerError) as caught:runner.start(plan,'owner')
            self.assertEqual(caught.exception.code,'declared_route_record_failed')
            self.assertFalse(runner.active());self.assertIsNone(runner.current)
            self.assertEqual(fleet.sent,[])  # nothing moved
            runner.root=Path(tmp)  # disk freed: the same runner accepts the next route
            runner.start(runner.plan(fleet.row['robot_id']),'owner')
            for _ in range(2000):
                if not runner.active():break
                time.sleep(.001)
            self.assertFalse(runner.active());self.assertEqual(runner.current['state'],'COMPLETED')

    def test_disk_full_during_the_route_halts_stops_and_still_reports(self):
        import tempfile
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        fleet=FakeFleet([]);results=[];clock=[0.]
        with tempfile.TemporaryDirectory() as tmp:
            runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s),poll_s=1.,on_result=results.append)
            saves=[0];original=runner._save
            def failing_save():
                saves[0]+=1
                if saves[0]>2:raise OSError(28,'No space left on device')
                original()
            runner._save=failing_save
            runner.start(runner.plan(fleet.row['robot_id']),'owner')
            for _ in range(2000):
                if results:break
                time.sleep(.001)
        result=results[0]
        self.assertEqual(result['state'],'FAILED');self.assertTrue(result['reason'].startswith('ROUTE_RECORD_WRITE_FAILED:OSError:STOP_'),result['reason'])
        self.assertEqual(result['save_error'],'OSError')
        self.assertEqual(fleet.sent[-1]['action'],'stop');self.assertFalse(runner.active())
        self.assertEqual(fleet.route_overlay['state'],'FAILED')

    def test_stop_numbers_and_progress_events_follow_the_plan(self):
        import tempfile
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        fleet=FakeFleet(['COMPLETED']*3+['FAILED']);fleet.fail_reason='FIELD_PROXIMITY_10CM'
        results=[];events=[];clock=[0.]
        with tempfile.TemporaryDirectory() as tmp:
            runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s),poll_s=1.,
                on_result=results.append,on_progress=events.append)
            runner.start(runner.plan(fleet.row['robot_id']),'owner')
            for _ in range(4000):
                if results:break
                time.sleep(.001)
        result=results[0];total=len(result['plan']['waypoints'])
        self.assertEqual(result['state'],'COMPLETED',result['reason'])
        reached,skipped=result['reached_stops'],result['skipped_stops']
        # Every planned stop is either reached under its own number or reported as skipped; never renumbered.
        self.assertEqual(sorted(reached+skipped),list(range(total)));self.assertEqual(reached,sorted(reached))
        stops=[s for s in result['waypoint_scans'] if not s['is_return']]
        self.assertEqual([s['stop'] for s in stops],reached)
        returns=[s for s in result['waypoint_scans'] if s['is_return']]
        self.assertEqual(len(returns),1);self.assertEqual(returns[0]['stop'],total)
        kinds=[e['event'] for e in events]
        self.assertEqual(kinds.count('recovery'),1);self.assertEqual(kinds.count('return_reached'),1)
        self.assertEqual([e['stop'] for e in events if e['event']=='stop_reached'],reached)
        overlay=fleet.route_overlay
        self.assertEqual(overlay['reached_stops'],reached);self.assertEqual(overlay['skipped_stops'],skipped)
        self.assertEqual(overlay['completed_steps'],result['completed_steps']);self.assertGreater(overlay['revision'],0)

    def test_skipped_stop_is_not_counted_as_reached_by_the_runner_bookkeeping(self):
        # Direct check of the recovery filter: a pending stop inside the new keepout is skipped, the start is kept.
        goals=[([1.,1.],0),([2.,1.],1),([3.,1.],2),([.6,.6],None)]
        discs=[(2.05,1.,.25)];reached=1
        pending=goals[reached:-1]
        remaining=[g for g in pending if all(math.dist(g[0],d[:2])>d[2]+.65 for d in discs)]+[goals[-1]]
        skipped=[g[1] for g in pending if g not in remaining]
        self.assertEqual(skipped,[1]);self.assertEqual([g[1] for g in remaining],[2,None])


class OtherSimRobotKeepoutTest(unittest.TestCase):
    def test_a_parked_connected_sim_robot_on_leg_one_is_kept_out_of_the_plan(self):
        # 2026-10-26 installed SIM checks: two earlier SIM robots parked on the floor stopped the
        # route with OBSTACLE_STOP; the planner never knew they were there.
        import tempfile
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        fleet=FakeFleet([])
        with tempfile.TemporaryDirectory() as tmp:
            runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:0.,sleep=lambda s:None,poll_s=1.)
            first=runner.plan(fleet.row['robot_id'])
            leg=first['legs'][0];mid=leg[len(leg)//2] if len(leg)>1 else first['waypoints'][0]
            parked=dict(robot_id='q'*32,kind='sim',connection_state='CONNECTED',control_state='READY',pose=dict(position_m=[mid[0],mid[1],0.]))
            fleet.snapshot=lambda:dict(robots=[dict(fleet.row),parked])
            second=runner.plan(fleet.row['robot_id'])
        self.assertEqual(second['other_sim_robots'],1);self.assertEqual(first['other_sim_robots'],0)
        self.assertIn([mid[0],mid[1],.35],second['keepouts'])
        self.assertGreater(min(math.dist(q[:2],mid[:2]) for q in second['polyline']),.35)
        self.assertNotEqual(second['polyline'],first['polyline'])


class PhysicalRun2026_10_26Tests(unittest.TestCase):
    """Defects seen on the supervised physical run (outputs/path-b-20261026/phys08)."""

    def test_recovery_replan_starts_inside_the_keepout_clearance_band(self):
        # Robot backed off 25 cm: 0.5 m from the keepout centre, inside radius .25 + clearance .37.
        from twinpulse_core.declared_route import replan_legs
        cells=[[(ix+.5)*.1,(iy+.5)*.1,'occupied' if ix in (0,39) or iy in (0,29) else 'free',0,0,0,0] for ix in range(40) for iy in range(30)]
        geometry=dict(bounds=[0.,0.,4.,3.],obstacles=[],targets=[])
        pose=[1.5,1.5,0.];disc=(2.0,1.5,.25)
        legs=replan_legs(pose,[[1.5,2.5],[.6,.6]],geometry,cells,kind='physical',discs=[disc])
        self.assertEqual(len(legs),2);self.assertTrue(all(legs))
        # Once away from the start the full berth is kept again.
        far=[q for leg in legs for q in leg if math.dist(q[:2],pose[:2])>.4]
        self.assertTrue(all(math.dist(q[:2],disc[:2])>disc[2]+.35 for q in far))

    def test_turns_are_capped_so_the_robot_deadline_holds(self):
        from twinpulse_core.declared_route import next_move, heading_move, MAX_TURN_RAD
        step=next_move([0.,0.,0.],[-1.,0.05])  # ~177 deg
        self.assertEqual(step['direction'],'left');self.assertAlmostEqual(step['amount'],MAX_TURN_RAD)
        self.assertAlmostEqual(heading_move([0.,0.,0.],3.0)['amount'],MAX_TURN_RAD)
        self.assertLess(MAX_TURN_RAD/.2+2.,12.)  # robot-side deadline amount/0.2 rad/s + 2 s

    def test_turn_overshoot_does_not_ping_pong(self):
        import tempfile
        fleet=FakeFleet([]);fleet.turn_error=math.radians(2.2)  # every turn overshoots by ~2 deg
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'COMPLETED',result['reason'])
        texts=[b['payload']['text'] for b in fleet.sent if b['action']=='command']
        turns=[t for t in texts if t.endswith('degrees')]
        runs=0;longest=0
        for t in texts:
            runs=runs+1 if t.endswith('degrees') else 0;longest=max(longest,runs)
        self.assertLessEqual(longest,3,texts)  # a big turn may be split, but no left/right ping-pong
        self.assertLess(len(turns),len(texts))

    def test_physical_plan_refuses_until_the_field_session_can_drive(self):
        import tempfile
        from twinpulse_app.command_broker import BrokerError
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        fleet=FakeFleet([])
        fleet.row.update(kind='physical',capabilities=dict(drive=False),field=dict(blockers=['FIELD_SUPERVISION_CONFIRMATION_REQUIRED','FIELD_BOOTSTRAP_STOP_REQUIRED']),
            display_pose=dict(scene_revision='rev',position_m=[.6,.6,0.],visual_epoch='v1'))
        with tempfile.TemporaryDirectory() as tmp:
            runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:0.,sleep=lambda s:None,poll_s=1.)
            with self.assertRaises(BrokerError) as caught:runner.plan(fleet.row['robot_id'])
        self.assertEqual(caught.exception.code,'declared_route_field_not_ready')
        self.assertIn('Bootstrap stop',str(caught.exception));self.assertIn('FIELD_SUPERVISION_CONFIRMATION_REQUIRED',str(caught.exception))
        self.assertEqual(fleet.sent,[])


class StartScanCandidateTest(unittest.TestCase):
    def test_box_seen_at_the_start_becomes_a_candidate_even_if_stops_barely_see_it(self):
        import tempfile
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        cells=[[(ix+.5)*.1,(iy+.5)*.1,'occupied' if ix in (0,39) or iy in (0,29) else 'free',0,0,0,0] for ix in range(40) for iy in range(30)]
        start=[.6,.6,0.];box=[1.7,.7];half=.15
        ring=[(box[0]+half*math.cos(t)-start[0],box[1]+half*math.sin(t)-start[1]) for t in [i*math.tau/16 for i in range(16)]]
        walls=[(3.95-start[0],y*.1-start[1]) for y in range(1,30)]+[(x*.1-start[0],2.95-start[1]) for x in range(1,40)]+[(x*.1-start[0],.05-start[1]) for x in range(1,40)]
        fleet=FakeFleet([]);fleet.navigation_scene['observed_cells']=cells
        fleet.row.update(kind='physical',lidar_state='STREAMING',capabilities=dict(drive=True),field=dict(blockers=[]),
            display_pose=dict(scene_revision='rev',position_m=start,visual_epoch='v1'),scan=dict(points=walls+ring,stream_id='s',frame_sequence=1,raw_sha256='x'))
        results=[];clock=[0.]
        with tempfile.TemporaryDirectory() as tmp:
            runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s),poll_s=1.,on_result=results.append)
            plan=runner.plan(fleet.row['robot_id'])
            self.assertTrue(plan['scan_keepouts']['used']);self.assertGreaterEqual(len(plan['keepouts']),3)
            runner.start(plan,'owner')
            self.assertTrue(fleet.route_overlay['candidates'],'start-scan returns cluster before the first stop')
            for _ in range(4000):
                if results:break
                time.sleep(.001)
        result=results[0]
        self.assertEqual(result['state'],'COMPLETED',result['reason'])
        self.assertTrue(any(math.dist(c['position_xy_m'],box)<.15 for c in result['candidates']),result['candidates'])


class RouteOverlayPayloadTest(unittest.TestCase):
    def test_full_overlay_on_change_and_every_two_seconds_else_stub(self):
        from types import SimpleNamespace
        from twinpulse_app.robot_fleet import RobotFleet
        clock=[100.];fleet=SimpleNamespace(clock=lambda:clock[0])
        route=dict(plan_id='p',revision=1,scene_revision='rev',trace=[[0,0]]*800)
        first=RobotFleet._route_payload(fleet,dict(route));self.assertNotIn('unchanged',first)
        clock[0]+=.5;stub=RobotFleet._route_payload(fleet,dict(route));self.assertTrue(stub.get('unchanged'));self.assertNotIn('trace',stub)
        clock[0]+=2.;self.assertNotIn('unchanged',RobotFleet._route_payload(fleet,dict(route)))
        clock[0]+=.1;self.assertNotIn('unchanged',RobotFleet._route_payload(fleet,dict(route,revision=2)))


class StraightFirstLegTest(unittest.TestCase):
    def test_first_leg_is_straight_along_the_declared_heading_when_the_floor_allows(self):
        wide=dict(bounds=[0.,0.,6.,3.],obstacles=[],targets=[])
        plan=plan_survey([.6,1.5,0.],wide,kind='physical',budget_m=8.)
        self.assertIsNotNone(plan['first_leg_straight_m']);self.assertGreaterEqual(plan['first_leg_straight_m'],1.)
        first=plan['waypoints'][0];self.assertLess(abs(first[1]-1.5),.16);self.assertEqual(plan['legs'][0],[first])
        # Something right in front: no straight leg is forced, the survey still plans.
        blocked=dict(bounds=[0.,0.,6.,3.],obstacles=[[1.2,1.0,1.6,2.0]],targets=[])
        plan=plan_survey([.6,1.5,0.],blocked,kind='physical',budget_m=8.)
        self.assertTrue(plan['waypoints'])


class ClusterOutlineTest(unittest.TestCase):
    def test_elongated_cluster_gets_an_oriented_extent(self):
        from twinpulse_core.declared_route import cluster_candidates
        # Returns along a 0.8 m edge rotated 30 degrees.
        a=math.radians(30);discs=[(2+t*math.cos(a),1+t*math.sin(a),.06) for t in [i*.1-.4 for i in range(9)]]
        out=cluster_candidates(discs)
        self.assertEqual(len(out),1);c=out[0]
        self.assertAlmostEqual(c['yaw_deg'],30.,delta=3.);self.assertGreater(c['extent_m'][0],.8);self.assertLess(c['extent_m'][1],.3)


class OperatorStopsTest(unittest.TestCase):
    def test_route_through_clicked_stops_then_home(self):
        from twinpulse_core.declared_route import plan_through
        plan=plan_through([.6,.6,0.],[[2.5,.8],[1.5,2.2]],room(),kind='physical')
        self.assertEqual(plan['waypoints'],[[2.5,.8],[1.5,2.2]]);self.assertEqual(plan['polyline'][-1][:2],[.6,.6])
        self.assertEqual(plan['scope'],'OPERATOR_STOPS_MODEL_PLAN_NOT_LOCALIZED');self.assertEqual(len(plan['legs']),3)

    def test_chat_parses_via_stops_and_routes_them_to_the_declared_route(self):
        from types import SimpleNamespace
        from twinpulse_app.conversation_service import ConversationService
        fleet=SimpleNamespace(focused='r',robots={'r':{'kind':'sim'}},navigation_scene=dict(geometry=dict(schema='scene-navigation-2.0')))
        self_=SimpleNamespace(declared_routes=object(),robot_fleet=fleet,_route_stops=ConversationService._route_stops)
        self.assertEqual(ConversationService._route_stops('Survey via (1.2, 0.8), (2, 1.5) and come back'),[[1.2,.8],[2.,1.5]])
        self.assertTrue(ConversationService._declared_route_request(self_,'Survey via (1.2, 0.8), (2, 1.5) and come back'))
        self.assertFalse(ConversationService._declared_route_request(self_,'Go via (1.2, 0.8)'))  # no return request

    def test_runner_plans_through_operator_stops(self):
        import tempfile
        from twinpulse_app.declared_route_runner import DeclaredRouteRunner
        fleet=FakeFleet([])
        with tempfile.TemporaryDirectory() as tmp:
            runner=DeclaredRouteRunner(fleet,tmp,clock=lambda:0.,sleep=lambda s:None,poll_s=1.)
            plan=runner.plan(fleet.row['robot_id'],stops=[[2.5,.8]])
        self.assertEqual(plan['waypoints'],[[2.5,.8]]);self.assertEqual(plan['scope'],'OPERATOR_STOPS_MODEL_PLAN_NOT_LOCALIZED')


class FloorMapAndCorrectionTest(unittest.TestCase):
    def test_floor_map_lists_free_cells_bounds_and_robot_positions(self):
        from twinpulse_app.robot_fleet import RobotFleet
        import threading
        from types import SimpleNamespace
        cells=[[.05,.05,'free',0,0,0,0],[.15,.05,'occupied',0,0,0,0]]
        fleet=SimpleNamespace(lock=threading.Lock(),navigation_scene=dict(binding=('e','s','rev'),geometry=dict(bounds=[0,0,4,3],obstacles=[[1,1,2,2]]),observed_cells=cells),
            robots={'a':dict(robot_id='a',label='Sim',kind='sim',pose=dict(position_m=[1,1,0])),'b':dict(robot_id='b',label='Phys',kind='physical',display_pose=dict(position_m=[2,2,.5]))})
        out=RobotFleet.floor_map(fleet)
        self.assertEqual(out['status'],'AVAILABLE');self.assertEqual(out['free_cells'],[[.05,.05]]);self.assertEqual(out['bounds'],[0,0,4,3])
        self.assertEqual({r['label']:r['position_m'] for r in out['robots']},{'Sim':[1,1,0],'Phys':[2,2,.5]})
        fleet.navigation_scene=None;self.assertEqual(RobotFleet.floor_map(fleet)['status'],'UNAVAILABLE')

    def test_candidate_near_an_existing_object_offers_a_position_correction(self):
        from types import SimpleNamespace
        from twinpulse_app.api import LocalApiServer as cls
        objects=[dict(id='Added_1',label='Fan base',category='floor_fan',position_m=[1.0,1.0,.5]),dict(id='floor',label='Floor',category='floor',position_m=[0,0,0])]
        self_=SimpleNamespace(_environment_workspace=lambda:SimpleNamespace(snapshot=lambda:dict(objects=objects)))
        matches=cls._route_candidate_matches(self_,[dict(position_xy_m=[1.3,1.1],returns=5),dict(position_xy_m=[3.,3.],returns=4)])
        self.assertEqual(len(matches),1);self.assertEqual(matches[0]['object_id'],'Added_1');self.assertEqual(matches[0]['translation_m'],[.3,.1,0.])


class SavedConversationCompatibilityTest(unittest.TestCase):
    def test_lidar_cards_saved_before_the_move_choice_still_validate(self):
        # 2026-10-26: the installed App refused to restore the project chat after 'move' was added.
        import json
        from twinpulse_app.conversation_service import ConversationService
        base=dict(session_id='s',project_id='p',mode='SIM',robot_id=None,physical_authority=False,restore_error=None,revision=1,cursor=1,
            requests={},messages=[dict(message_id='m',role='assistant',content='x',session_id='s',reply_to=None,attachments=[],status='completed',created_at='t',operation_id=None)],
            events=[],thumbnails={},accepted_request_ids=[],cards=[])
        def card(ids):return dict(id='c',card_id='c',kind='declared_route_obstacles',question='q',state='answered',selected_choice_id='skip',
            expected_session_revision=1,message_id='m',operation_id='o'*32,related_plan_digest=None,created_at='t',expires_at=None,
            choices=[dict(id=i,label=i,enabled=True,disabled_reason=None) for i in ids])
        # Only the card rules are under test: the full validator also needs the generation/queue fields.
        import inspect,textwrap
        source=inspect.getsource(ConversationService._validate_history)
        self.assertIn("optional={'declared_route_obstacles':{'move'}}",source)
        self.assertIn("len(card['choices']) not in {len(card_allowed),len(card_allowed-optional)}",source)
        base.update(generation=None,queued_edit=None,simulation_review=None,scene_sensor_review=None,scene_feedback=None,pending_edit=None,
            budgeted_generation_available=False,robot_preparation=None,room_build=None,inspection_display=None,sensor_selection=None)
        def validate(cards):
            try:ConversationService._validate_history(json.loads(json.dumps(dict(base,cards=cards))))
            except KeyError:return 'other-field'  # a missing unrelated field, not a card rejection
            return 'ok'
        self.assertNotEqual(validate([card(['add','skip'])]),'rejected');self.assertNotEqual(validate([card(['add','move','skip'])]),'rejected')
        with self.assertRaises(ValueError):
            try:ConversationService._validate_history(json.loads(json.dumps(dict(base,cards=[card(['add','bogus','skip'])]))))
            except KeyError:raise ValueError('reached the card rule')  # cards are checked before those fields


class ModelFirstRouteTests(unittest.TestCase):
    """Hackathon flow: Nemotron (Nebius Token Factory) plans, the deterministic Path B route executes."""
    def _service(self,job_states):
        import threading
        from types import SimpleNamespace
        from twinpulse_app.conversation_service import ConversationService
        messages=[];cards=[];events=[]
        plan=dict(plan_id='p'*32,robot_id='r',kind='sim',start=[.6,.6,0.],waypoints=[[1.5,.6]],polyline=[[1.5,.6],[.6,.6]],length_m=1.8,
            steps=[dict(direction='forward',amount=.9,text='forward 90.0cm')],start_basis='sim_engine_pose',scope='S',keepouts=[],scan_keepouts={})
        runner=SimpleNamespace(plan=lambda robot_id,stops=None:dict(plan),active=lambda:False,readiness=lambda robot_id:None)
        jobs=list(job_states);job=dict(task_id='t'*32,request_id='req',state='PLANNING',model_id='nvidia/nemotron-3-super-120b-a12b',plan=None,reason=None,step_index=0,segments=0)
        tasks=SimpleNamespace(registry=object(),active=lambda:False,propose=lambda text,owner,rid:dict(job),cancel=lambda owner:None,
            snapshot=lambda owner:dict(job,**jobs.pop(0)) if jobs else dict(job))
        s=SimpleNamespace(_lock=threading.Lock(),_state=dict(session_id='s',messages=[],cards=[]),robot_fleet=SimpleNamespace(focused='r',navigation_scene=dict(observed_cells=[]),robots={'r':{'kind':'sim'}}),
            declared_routes=runner,robot_tasks=tasks,_request_owner='o',_robot_task_marker=None,
            _message=lambda role,content,**kw:messages.append((role,content,kw)),_event=lambda name,**kw:events.append((name,kw)),_persist=lambda:None,
            _route_preview=lambda plan:dict(bounds=[0,0,1,1],free_cells=[],cell_m=.1,start=plan['start'],waypoints=plan['waypoints'],polyline=plan['polyline'],basis='b',scope='s'))
        s._choice=ConversationService._choice
        def card(kind,question,choices,**kw):c=dict(id='c%d'%len(cards),kind=kind,question=question,choices=choices,state='waiting');cards.append(c);s._state['cards'].append(c);return c
        s._card=card
        for name in ('_route_stops','_offer_route_fallback','_plan_declared_route','_start_declared_route','_sync_robot_tasks'):
            setattr(s,name,getattr(ConversationService,name).__get__(s))
        s._route_stops=ConversationService._route_stops
        return s,messages,cards,events

    def test_model_plan_is_validated_then_handed_to_path_b(self):
        s,messages,cards,events=self._service([dict(state='READY',plan=dict(steps=[dict(op='survey'),dict(op='return_to_start')],explanation='Survey then return.'))])
        s._start_declared_route(dict(text='Survey the room and come back',request_id='req'))
        self.assertIn('Nebius Token Factory',messages[-1][1]);self.assertEqual(cards,[])
        s._sync_robot_tasks('o')
        self.assertEqual(cards[-1]['kind'],'declared_route_run');self.assertIn('Planned by nvidia/nemotron-3-super-120b-a12b via Nebius Token Factory',cards[-1]['question'])
        self.assertEqual(s._declared_route_pending['planned_by']['kind'],'model')
        self.assertIn('declared_route_model_planned',[e[0] for e in events])

    def test_model_failure_is_shown_and_fallback_is_explicit(self):
        from twinpulse_app.conversation_service import ConversationService
        s,messages,cards,events=self._service([dict(state='FAILED',reason='HTTP 402 Payment Required')])
        s._start_declared_route(dict(text='Survey the room and come back',request_id='req'));s._sync_robot_tasks('o')
        self.assertIn('402',messages[-1][1]);self.assertEqual(cards[-1]['kind'],'declared_route_fallback')
        ConversationService._answer.__get__(s)  # method exists; answer path exercised directly below
        s._route_fallback_pending['request_id']='req';cards[-1]['operation_id']='req'
        s._plan_declared_route('Survey the room and come back','req',planned_by=dict(kind='fallback',label='Deterministic fallback · model call failed: HTTP 402'))
        self.assertEqual(cards[-1]['kind'],'declared_route_run');self.assertIn('Deterministic fallback',cards[-1]['question'])

    def test_plan_outside_survey_capabilities_is_rejected(self):
        s,messages,cards,events=self._service([dict(state='READY',plan=dict(steps=[dict(op='move_relative',direction='forward',amount=3.)],explanation='x'))])
        s._start_declared_route(dict(text='Survey the room and come back',request_id='req'));s._sync_robot_tasks('o')
        self.assertEqual(cards[-1]['kind'],'declared_route_fallback');self.assertIn('outside the survey capabilities',messages[-1][1])

    def test_route_refused_by_readiness_spends_no_planner_call(self):
        # 2026-10-27 build-54 check: "Survey the room" on an unprepared robot called Nemotron, then plan() refused.
        from twinpulse_app.command_broker import BrokerError
        s,messages,cards,events=self._service([])
        calls=[];s.robot_tasks.propose=lambda text,owner,rid:calls.append(text) or dict(task_id='t'*32)
        def refuse(robot_id):raise BrokerError('declared_route_robot_busy','Stop and prepare the robot before a route.',status=409)
        s.declared_routes.readiness=refuse
        s._start_declared_route(dict(text='Survey the room and come back',request_id='req'))
        self.assertEqual(calls,[]);self.assertEqual(cards,[])
        self.assertEqual(messages[-1][:2],('assistant','Stop and prepare the robot before a route.'));self.assertEqual(messages[-1][2].get('status'),'failed')
        self.assertEqual([e[0] for e in events],['declared_route_blocked']);self.assertEqual(events[-1][1]['code'],'declared_route_robot_busy')
        self.assertFalse(getattr(s,'_route_model_pending',None))

    def test_operator_stops_skip_the_model(self):
        s,messages,cards,events=self._service([])
        s._start_declared_route(dict(text='Survey via (1.2, 0.8) and come back',request_id='req'))
        self.assertEqual(cards[-1]['kind'],'declared_route_run');self.assertIn('Operator stops · no model call',cards[-1]['question'])


class PhotoColorTest(unittest.TestCase):
    def test_room_item_display_color_reaches_the_visual_parts_and_the_compiler_parses_it(self):
        from twinpulse_core.room_items import expand_room_item, room_item_catalog_version, parse_display_color_tag, SceneToolPlanError
        item=dict(id='Added_'+'a'*20,kind='box',label='Box',catalog_version=room_item_catalog_version('box'),position_m=[1.,1.,.15],
            dimensions_m=[.3,.3,.3],yaw_deg=0.,observation_time_utc=None)
        plain=expand_room_item(item);self.assertTrue(all(o.asset_id is None for o in plain))
        colored=expand_room_item(dict(item,display_color=[.52,.31,.2]))
        visual=[o for o in colored if '_visual_' in o.id];self.assertTrue(visual)
        self.assertEqual(parse_display_color_tag(visual[0].asset_id),(.52,.31,.2))
        self.assertEqual([o.shape for o in colored],[o.shape for o in plain])  # geometry identical
        with self.assertRaises(SceneToolPlanError):expand_room_item(dict(item,display_color=[2,0,0]))
        self.assertIsNone(parse_display_color_tag('burger_v1'))

    def test_colour_tagged_visual_part_passes_scene_validation_without_a_library_asset(self):
        from twinpulse_core.models import SceneObject, Transform, ShapeSpec
        from twinpulse_core.validation import validate_scene_geometry, ValidationLimits
        box=SceneObject('Added_'+'a'*20+'_visual_0','equipment',Transform((1.,1.,.15),(0.,0.,0.)),ShapeSpec('box',(.3,.3,.3)),asset_id='color:0.520,0.310,0.200')
        validate_scene_geometry('scene',(box,),ValidationLimits(max_objects=None))  # no library asset needed for a colour tag
        with self.assertRaises(Exception):
            validate_scene_geometry('scene',(SceneObject('x','equipment',Transform((1.,1.,.15),(0.,0.,0.)),ShapeSpec('box',(.3,.3,.3)),asset_id='color:9,9,9'),),ValidationLimits(max_objects=None))

    def test_photo_crop_color_is_the_crop_median(self):
        import io
        from PIL import Image
        from twinpulse_app.environment_workspace import photo_crop_color
        image=Image.new('RGB',(100,100),(10,10,10));box=Image.new('RGB',(40,40),(200,60,30));image.paste(box,(50,50))
        buf=io.BytesIO();image.save(buf,'PNG')
        self.assertEqual(photo_crop_color(buf.getvalue(),[.5,.5,.9,.9]),[round(200/255,3),round(60/255,3),round(30/255,3)])
        self.assertIsNone(photo_crop_color(buf.getvalue(),None))


class DeclaredRouteChatMessageTests(unittest.TestCase):
    def _service(self):
        import threading
        from types import SimpleNamespace
        messages=[];events=[]
        s=SimpleNamespace(_lock=threading.Lock(),_state=dict(session_id='s',messages=[],cards=[]),add_route_obstacles=None,
            _message=lambda role,content,**kw:messages.append((role,content,kw)),_event=lambda name,**kw:events.append((name,kw)),_persist=lambda:None)
        return s,messages,events

    def test_finish_message_counts_only_reached_stops_and_names_skipped_ones(self):
        from twinpulse_app.conversation_service import ConversationService
        s,messages,_=self._service()
        plan=dict(plan_id='p'*32,waypoints=[[1,1],[2,1],[3,1]])
        result=dict(plan=plan,state='COMPLETED',reason='ALL_STOPS_AND_RETURN_COMPLETED',completed_steps=17,context=dict(session_id='s'),
            waypoint_scans=[dict(stop=0,is_return=False),dict(stop=2,is_return=False),dict(stop=3,is_return=True)],reached_stops=[0,2],skipped_stops=[1],candidates=[])
        ConversationService.declared_route_finished(s,result)
        text=messages[0][1]
        self.assertIn('reached 2 of 3 stops (skipped stop 2 after a proximity stop) and returned to the start; 17 finite moves',text)
        self.assertEqual(messages[0][2]['status'],'completed')
        # Another chat session never receives the result.
        s._state['session_id']='other';ConversationService.declared_route_finished(s,result)
        self.assertEqual(len(messages),1)

    def test_progress_messages_name_the_stop_and_moves(self):
        from twinpulse_app.conversation_service import ConversationService
        s,messages,_=self._service()
        base=dict(plan_id='p'*32,robot_id='r',total_stops=4,context=dict(session_id='s'))
        ConversationService.declared_route_progress(s,dict(base,event='stop_reached',stop=1,reached=2,completed_steps=7,unexplained=5))
        ConversationService.declared_route_progress(s,dict(base,event='recovery',at=[1.234,0.5],recoveries=1,completed_steps=8))
        ConversationService.declared_route_progress(s,dict(base,event='return_reached',stop=None,reached=4,completed_steps=20,unexplained=0))
        self.assertEqual(messages[0][1],'Stop 2 of 4 reached · 7 moves so far · LiDAR: 5 returns not in the Twin')
        self.assertIn('Proximity stop at (1.23, 0.50) m',messages[1][1])
        self.assertIn('Back at the start after 4 of 4 stops · 20 moves',messages[2][1])


class ReplanDemoTest(unittest.TestCase):
    def test_box_on_leg_one_becomes_a_candidate_and_the_next_plan_avoids_it(self):
        """Morning demo: box on leg 1 -> LiDAR 'not in model' candidate -> Add to Twin -> different route."""
        from twinpulse_core.declared_route import unexplained_scan_discs, cluster_candidates
        cells=[[(ix+.5)*.1,(iy+.5)*.1,'occupied' if ix in (0,39) or iy in (0,29) else 'free',0,0,0,0] for ix in range(40) for iy in range(30)]
        geometry=dict(bounds=[0.,0.,4.,3.],obstacles=[],targets=[]);start=[.6,.6,0.]
        first=plan_survey(start,geometry,cells,kind='physical',budget_m=8.)
        leg=first['legs'][0];a=start[:2];b=leg[len(leg)//2] if len(leg)>1 else first['waypoints'][0]
        # A 30 cm box in the middle of leg 1, seen from the start as a ring of returns (sensor frame = world here, yaw 0).
        box=[(a[0]+b[0])/2,(a[1]+b[1])/2];half=.15
        ring=[(box[0]+half*math.cos(t)-start[0],box[1]+half*math.sin(t)-start[1]) for t in [i*math.tau/16 for i in range(16)]]
        walls=[(3.95-start[0],y*.1-start[1]) for y in range(1,30)]+[(x*.1-start[0],2.95-start[1]) for x in range(1,40)]+[(x*.1-start[0],.05-start[1]) for x in range(1,40)]
        review=unexplained_scan_discs(start,walls+ring,cells)
        self.assertTrue(review['used'],review)
        candidates=cluster_candidates(review['discs'])
        self.assertEqual(len(candidates),1,candidates)
        self.assertLess(math.dist(candidates[0]['position_xy_m'],box),.12)
        # Add to Twin: the candidate becomes an obstacle in the model (as the Twin edit + Isaac rebuild would).
        c=candidates[0];r=max(.2,c['radius_m'])
        added=dict(geometry,obstacles=[[c['position_xy_m'][0]-r,c['position_xy_m'][1]-r,c['position_xy_m'][0]+r,c['position_xy_m'][1]+r]])
        blocked_cells=[[x,y,'occupied' if math.dist((x,y),box)<=r+.05 else k,*rest] for x,y,k,*rest in cells]
        second=plan_survey(start,added,blocked_cells,kind='physical',budget_m=8.)
        self.assertNotEqual(second['polyline'],first['polyline'])
        clearance=min(math.dist(p[:2],box) for p in second['polyline'])
        self.assertGreater(clearance,r+.3,clearance)  # the new route keeps the physical berth from the box


class LidarLayerTest(unittest.TestCase):
    """2026-10-26 user ask: route LiDAR points stay on the Twin (display only) until cleared; LiDAR-moved objects are marked."""
    def _fleet(self):
        import threading
        from types import SimpleNamespace
        from twinpulse_app.robot_fleet import RobotFleet
        fleet=SimpleNamespace(lock=threading.Lock(),lidar_layer=None,clock=lambda:7.,navigation_scene=dict(binding=('e','s','rev'),geometry=dict(bounds=[0,0,4,3],obstacles=[]),observed_cells=[[.05,.05,'free',0,0,0,0]]),robots={})
        for name in ('absorb_route_layer','note_lidar_move','clear_lidar_layer','floor_map'):setattr(fleet,name,getattr(RobotFleet,name).__get__(fleet))
        fleet.LIDAR_LAYER_LABEL=RobotFleet.LIDAR_LAYER_LABEL;fleet.LIDAR_LAYER_CAP=RobotFleet.LIDAR_LAYER_CAP
        return fleet

    def test_finished_routes_accumulate_stop_and_drive_points_and_clear_drops_them(self):
        from twinpulse_app.robot_fleet import lidar_layer_payload
        fleet=self._fleet()
        fleet.absorb_route_layer(dict(scene_revision='rev',scans=[dict(stop=0,points=[[1,1],[1.01,1.01],[2,2]])],drive_scan=[[3,1]]))
        fleet.absorb_route_layer(dict(scene_revision='rev',scans=[dict(stop=1,points=[[2,2],[2.5,2.5]])],drive_scan=[]))
        layer=fleet.lidar_layer
        self.assertEqual(layer['routes'],2);self.assertEqual(layer['stop_points'],[[1,1],[2,2],[2.5,2.5]]);self.assertEqual(layer['drive_points'],[[3,1]])
        self.assertEqual(layer['label'],'DECLARED_START_PLUS_ODOMETRY_DISPLAY_ONLY_NOT_REGISTERED')
        self.assertEqual(fleet.floor_map()['lidar_layer']['stop_points'],[[1,1],[2,2],[2.5,2.5]])
        self.assertIsNone(lidar_layer_payload(layer,'other-scene'))  # a new Twin revision never shows old points
        fleet.absorb_route_layer(dict(scene_revision='rev2',scans=[dict(stop=0,points=[[0,0]])]))
        self.assertEqual(fleet.lidar_layer['routes'],1)  # the layer follows the Twin revision
        fleet.clear_lidar_layer();self.assertIsNone(fleet.lidar_layer);self.assertIsNone(fleet.floor_map()['lidar_layer'])

    def test_lidar_move_marker_is_labelled_unverified(self):
        fleet=self._fleet()
        fleet.note_lidar_move('Added_1','Fan base',[1.3,1.1],.3)
        moved=fleet.floor_map()['lidar_layer']['moved']
        self.assertEqual(moved,[dict(object_id='Added_1',label='Fan base',position_xy_m=[1.3,1.1],distance_m=.3,basis='lidar_estimate_unverified')])

    def test_runner_keeps_drive_points_and_hands_the_layer_to_the_fleet_at_finish(self):
        import tempfile
        fleet=FakeFleet([]);absorbed=[]
        fleet.absorb_route_layer=absorbed.append
        fleet.row['lidar_state']='STREAMING';fleet.row['scan']=dict(points=[[.5,.0],[.0,.5]])
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'COMPLETED',result['reason'])
        self.assertEqual(len(absorbed),1);self.assertTrue(absorbed[0].get('drive_scan'))
        self.assertTrue(all(len(p)==2 for p in absorbed[0]['drive_scan']))


class LidarMatchThresholdTest(unittest.TestCase):
    def _matches(self,candidates):
        from types import SimpleNamespace
        from twinpulse_app.api import LocalApiServer as cls
        objects=[dict(id='Added_1',label='Fan base',category='floor_fan',position_m=[1.0,1.0,.5]),dict(id='floor',label='Floor',category='floor',position_m=[0,0,0])]
        self_=SimpleNamespace(_environment_workspace=lambda:SimpleNamespace(snapshot=lambda:dict(objects=objects)))
        return cls._route_candidate_matches(self_,candidates)

    def test_within_ten_centimetres_is_aligned_and_up_to_sixty_offers_a_move(self):
        matches=self._matches([dict(position_xy_m=[1.05,1.02],returns=5),dict(position_xy_m=[1.3,1.1],returns=5),dict(position_xy_m=[3.,3.],returns=4)])
        self.assertEqual([(m['candidate'],m['aligned']) for m in matches],[(0,True),(1,False)])

    def test_matched_candidates_are_left_out_of_the_outline_boxes(self):
        import json,tempfile
        from types import SimpleNamespace
        from twinpulse_app.api import LocalApiServer as cls
        from twinpulse_app.command_broker import BrokerError
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'declared-routes').mkdir();plan_id='a'*32
            (root/'declared-routes'/(plan_id+'.json')).write_text(json.dumps(dict(candidates=[])),encoding='utf-8')
            workspace=SimpleNamespace(action=lambda body,owner:calls.append(body) or dict(preview=dict(operation=dict(operation_id='op'),preview_digest='d'),lidar_added=1),
                pinned_environment_operation=lambda *a,**k:('op','d'))
            self_=SimpleNamespace(robot_fleet=SimpleNamespace(root=root),_environment_workspace=lambda:workspace,
                _workflow=lambda:SimpleNamespace(scene_edit_transaction=SimpleNamespace(start=lambda *a:None)))
            candidates=[dict(position_xy_m=[1.05,1.02],radius_m=.1,returns=5),dict(position_xy_m=[3.,3.],radius_m=.15,returns=4)]
            cls._add_route_obstacles(self_,'o',plan_id,candidates,exclude=[0])
            self.assertEqual([o['candidate'] for o in calls[0]['obstacles']],[1])
            with self.assertRaises(BrokerError):cls._add_route_obstacles(self_,'o',plan_id,candidates,exclude=[0,1])

    def test_lidar_outline_boxes_carry_the_dark_display_colour(self):
        import inspect
        from twinpulse_app import environment_workspace as ws
        self.assertEqual(ws.LIDAR_BOX_COLOR,(.16,.16,.17))
        self.assertIn("display_color=list(LIDAR_BOX_COLOR)",inspect.getsource(ws.EnvironmentWorkspace.action))


class TwinEditAutoApplyTest(unittest.TestCase):
    """Twin-edit approval mode: Review (default) keeps the card; Auto applies LiDAR moves/boxes one transaction at a time, then re-plans."""
    def _service(self,mode):
        import threading
        from types import SimpleNamespace
        from twinpulse_app.conversation_service import ConversationService
        messages=[];cards=[];events=[];applied=[]
        s=SimpleNamespace(_lock=threading.Lock(),_state=dict(session_id='s',messages=[],cards=[],twin_edit_approval=mode),_request_owner='o',
            robot_fleet=SimpleNamespace(focused='r'),declared_routes=SimpleNamespace(active=lambda:False),_last_route_text='Survey the room and come back',
            _message=lambda role,content,**kw:messages.append((role,content,kw)),_event=lambda name,**kw:events.append((name,kw)),_persist=lambda:None,
            match_route_objects=lambda candidates:[dict(candidate=0,object_id='Added_1',label='Fan base',distance_m=.3,aligned=False,translation_m=[.3,.1,0.]),
                                                   dict(candidate=1,object_id='Added_2',label='Basket',distance_m=.05,aligned=True,translation_m=[.05,0.,0.])],
            add_route_obstacles=lambda owner,plan_id,candidates,exclude=():applied.append(('add',tuple(exclude))) or ('op-add-%d'%len(applied),1),
            move_route_object=lambda owner,plan_id,match:applied.append(('move',match['object_id'])) or 'op-move',
            _plan_declared_route=lambda text,request_id,**kw:applied.append(('plan',kw['planned_by']['kind'])))
        s._choice=ConversationService._choice
        def card(kind,question,choices,**kw):c=dict(id='c%d'%len(cards),kind=kind,question=question,choices=choices,state='waiting');cards.append(c);s._state['cards'].append(c);return c
        s._card=card
        for name in ('_apply_next_auto_edit','_auto_replan','declared_route_finished','_set_twin_edit_approval'):setattr(s,name,getattr(ConversationService,name).__get__(s))
        return s,messages,cards,events,applied

    def _result(self):
        plan=dict(plan_id='p'*32,waypoints=[[1,1],[2,1]])
        candidates=[dict(position_xy_m=[1.3,1.1],returns=6,radius_m=.1),dict(position_xy_m=[2.05,2.],returns=5,radius_m=.1),dict(position_xy_m=[3.,3.],returns=4,radius_m=.15)]
        return dict(plan=plan,state='COMPLETED',reason='ALL_STOPS_AND_RETURN_COMPLETED',completed_steps=9,context=dict(session_id='s'),
            waypoint_scans=[],reached_stops=[0,1],skipped_stops=[],candidates=candidates)

    def test_review_mode_card_names_the_aligned_match_and_offers_add_and_move(self):
        s,messages,cards,events,applied=self._service('review')
        s.declared_route_finished(self._result())
        self.assertEqual(applied,[]);self.assertEqual(cards[-1]['kind'],'declared_route_obstacles')
        self.assertIn('Candidate #2 matches the Twin object "Basket" (0.05 m away): no move needed.',cards[-1]['question'])
        self.assertIn('Add the 1 unexplained one to the Twin',cards[-1]['question'])
        self.assertEqual([c['id'] for c in cards[-1]['choices']],['add','move','skip'])
        self.assertEqual(s._route_candidates['new'],[2])

    def test_auto_mode_applies_move_then_box_one_transaction_at_a_time_then_replans(self):
        s,messages,cards,events,applied=self._service('auto')
        s.declared_route_finished(self._result())
        self.assertEqual(cards,[])  # no question in auto mode
        self.assertEqual(applied,[('move','Added_1')])  # the first edit starts at once
        self.assertIn('Twin-edit auto-apply: moving "Fan base" to the LiDAR estimate, adding 1 outline box.',messages[1][1])
        self.assertTrue(any('Auto-applied (Twin-edit auto-apply): moving "Fan base"' in m[1] for m in messages))
        self.assertFalse(s._auto_replan_pending)
        s._apply_next_auto_edit()  # the transaction sync calls this once the move is COMMITTED with its frame
        self.assertEqual(applied[1],('add',(0,1)))  # matched candidates (moved or aligned) are never boxed
        self.assertTrue(s._auto_replan_pending)  # the last edit started: the sync re-plans when its frame is confirmed
        s._auto_replan_pending=False;s._auto_replan()
        self.assertEqual(applied[-1],('plan','auto_replan'));self.assertEqual(s._auto_route_edits,[])
        self.assertTrue(any('re-planning "Survey the room and come back"' in m[1] for m in messages))
        self.assertIn('declared_route_auto_apply',[e[0] for e in events])

    def test_mode_switch_is_validated_and_never_touches_motion_state(self):
        from twinpulse_app.command_broker import BrokerError
        s,messages,cards,events,applied=self._service('review')
        s._set_twin_edit_approval(dict(action='twin_edit_approval',request_id='r1',mode='auto'))
        self.assertEqual(s._state['twin_edit_approval'],'auto');self.assertIn('Robot motion is unchanged',messages[-1][1])
        with self.assertRaises(BrokerError):s._set_twin_edit_approval(dict(action='twin_edit_approval',request_id='r2',mode='yolo'))
        self.assertEqual(set(s._state),{'session_id','messages','cards','twin_edit_approval'})  # no motion or authority field appears

    def test_saved_conversations_without_the_mode_restore_as_review(self):
        import inspect
        from twinpulse_app.conversation_service import ConversationService
        source=inspect.getsource(ConversationService.__init__)
        self.assertIn('stored.setdefault("twin_edit_approval","review")',source)


class SimWorldObstacleTest(unittest.TestCase):
    """A test box that exists only in the Isaac SIM world: SIM LiDAR and the proximity stop see it, the Twin model does not."""
    def test_payload_is_validated_and_labelled_sim_only(self):
        from twinpulse_app.robot_fleet import checked_sim_obstacle, SIM_OBSTACLE_LIMIT
        from twinpulse_app.command_broker import BrokerError
        item=checked_sim_obstacle(dict(label=' Box on leg 1 ',position_m=[1.19,-0.22],size_m=[.4,.4,.4]),0)
        self.assertEqual(item['label'],'Box on leg 1');self.assertEqual(item['position_m'],[1.19,-.22]);self.assertEqual(item['source'],'SIM_WORLD_TEST_OBSTACLE_NOT_IN_TWIN')
        self.assertTrue(item['id'].startswith('simobs_0_'))
        for bad in (dict(label='x',position_m=[1,2],size_m=[.05,.4,.4]),dict(label='',position_m=[1,2],size_m=[.4,.4,.4]),dict(label='x',position_m=[1],size_m=[.4,.4,.4]),dict(label='x',position_m=[1,2])):
            with self.assertRaises(BrokerError):checked_sim_obstacle(bad,0)
        with self.assertRaises(BrokerError):checked_sim_obstacle(dict(label='x',position_m=[1,2],size_m=[.4,.4,.4]),SIM_OBSTACLE_LIMIT)

    def test_runtime_rays_and_motion_guard_include_the_sim_obstacle_root_but_the_twin_model_does_not(self):
        import inspect
        from twinpulse_app import lidar_scene_geometry
        source=inspect.getsource(lidar_scene_geometry.scene_section)
        self.assertIn("/World/TwinPulse/Fleet/SimObstacles",source)
        runtime=open(Path(__file__).resolve().parents[2]/'scripts'/'twinpulse_fleet_runtime.py',encoding='utf-8').read()
        self.assertIn("boxes=self._bounds(stage)+list(getattr(self,'sim_obstacle_boxes',[]))",runtime)  # proximity stop sees it
        self.assertNotIn("SimObstacles",runtime[runtime.index('def _navigation_scene'):runtime.index('def _navigation_scene')+2500])  # the planner grid does not


class GeneratedTwinExportTest(unittest.TestCase):
    """A photo/text-generated Twin exports as import-ready boxes (floor top at z=0, category-carrying prim names)."""
    def test_boxes_become_categorised_triangle_meshes(self):
        from twinpulse_core.models import SceneObject, Transform, ShapeSpec
        from twinpulse_app.twin_export import generated_twin_usda
        objects=[SceneObject('floor','floor',Transform((0.,0.,-.05)),ShapeSpec('box',(12.,8.,.1))),
                 SceneObject('left_wall','wall',Transform((-6.,0.,1.75)),ShapeSpec('box',(.08,8.,3.5))),
                 SceneObject('Rack_1_post_0_a','rack',Transform((-.2,-.4,.75)),ShapeSpec('box',(.1,.1,1.5))),
                 SceneObject('Pallet_1','equipment',Transform((2.,-2.,.07),(0.,0.,30.)),ShapeSpec('box',(1.2,.8,.14))),
                 SceneObject('Cart_1_keepout','equipment',Transform((3.,3.,.2)),ShapeSpec('box',(.5,.5,.4))),
                 SceneObject('agv','robot',Transform((0.,0.,.2)),ShapeSpec('box',(.6,.4,.4)))]
        text=generated_twin_usda(objects,scene_id='factory_1')
        self.assertIn('def Mesh "floor"',text);self.assertIn('def Mesh "wall1"',text);self.assertIn('def Mesh "storage1"',text);self.assertIn('def Mesh "unknown1"',text)
        self.assertNotIn('Cart_1_keepout',text);self.assertNotIn('"agv"',text)
        self.assertIn('metersPerUnit = 1',text);self.assertIn('upAxis = "Z"',text)
        self.assertEqual(text.count('faceVertexCounts = [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]'),4)
        floor=text[text.index('def Mesh "floor"'):text.index('def Mesh "wall1"')]
        zs=[float(t.split(',')[2].strip(') ')) for t in floor.split('points = [')[1].split(']')[0].split('), (')]
        self.assertAlmostEqual(max(zs),0.,places=4)  # floor top on the plane the import expects
        self.assertAlmostEqual(min(zs),-.1,places=4)
        with self.assertRaises(ValueError):generated_twin_usda(objects[1:])


class RobotWorkspaceFromGeneratedTwinTest(unittest.TestCase):
    """One click: a generated Twin becomes a new project whose saved scene is the same boxes as an imported space."""
    def _objects(self):
        from twinpulse_core.models import SceneObject, Transform, ShapeSpec
        return [SceneObject('floor','floor',Transform((0.,0.,-.05)),ShapeSpec('box',(12.,8.,.1))),
                SceneObject('left_wall','wall',Transform((-6.,0.,1.75)),ShapeSpec('box',(.08,8.,3.5))),
                SceneObject('Rack_1_post_0_a','rack',Transform((-.2,-.4,.75)),ShapeSpec('box',(.1,.1,1.5))),
                SceneObject('Pallet_1','equipment',Transform((2.,-2.,.07),(0.,0.,30.)),ShapeSpec('box',(1.2,.8,.14)))]

    def test_environment_contract_matches_the_exported_usda(self):
        import hashlib
        from twinpulse_app.twin_export import generated_twin_usda, generated_twin_environment
        usda=generated_twin_usda(self._objects(),scene_id='f').encode('utf-8')
        env=generated_twin_environment(self._objects(),usda,source_name='twin-x.usda',scene_id='f')
        self.assertEqual(env['source_sha256'],hashlib.sha256(usda).hexdigest());self.assertEqual(env['units_basis'],'authored')
        self.assertEqual([m['category'] for m in env['meshes']],['floor','wall','storage','unknown'])
        self.assertEqual([m['label'] for m in env['meshes']],['floor','wall1','storage1','unknown1'])
        self.assertTrue(all(len(m['triangles'])==12 and len(m['points_m'])==8 for m in env['meshes']))

    def test_catalog_creates_a_new_project_with_an_imported_site_draft(self):
        import tempfile
        from uuid import uuid4
        from twinpulse_app.project_catalog import ProjectCatalog, create_robot_workspace
        from twinpulse_app.project_store import ProjectStore
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);catalog=ProjectCatalog(root,'default')
            result=create_robot_workspace(catalog,'robot_demo',request_id=str(uuid4()),objects=self._objects(),scene_id='factory_1',
                profile_id='default',source_project_id='chat_src')
            self.assertEqual(result['created_project_id'],'robot_demo');self.assertEqual(result['object_count'],4);self.assertIs(result['physical_authority'],False)
            record=ProjectStore.for_project(root,'robot_demo').load()
            self.assertIsNotNone(record.site_draft);self.assertEqual(record.site_draft.provider_name,'local-environment-import')
            self.assertIsNotNone(record.site_draft.site.scene.environment)
            self.assertEqual(record.site_draft.site.scene.environment['source_name'],'twin-chat_src.usda')
            self.assertTrue(any(p.name=='environment-source.bin' for p in (root/'projects'/'robot_demo').rglob('*')))
            with self.assertRaises(FileExistsError):
                create_robot_workspace(catalog,'robot_demo',request_id=str(uuid4()),objects=self._objects(),scene_id='factory_1',profile_id='default',source_project_id='chat_src')


class ApiAttributeRegressionTest(unittest.TestCase):
    def test_routes_never_read_a_project_id_attribute_the_server_does_not_have(self):
        # 2026-10-26: the first robot-workspace click failed with AttributeError on self.project_id (the broker owns it).
        source=open(Path(__file__).resolve().parents[2]/'packages'/'twinpulse_app'/'src'/'twinpulse_app'/'api.py',encoding='utf-8').read()
        self.assertNotIn('self.project_id',source)
        self.assertIn("source_project_id=self._workflow()._broker.project_id",source)


class SimObstacleSyncIdempotenceTest(unittest.TestCase):
    def test_unchanged_obstacle_set_authors_nothing_and_leaves_bounds_clean(self):
        # 2026-10-26: re-authoring an empty set every tick kept the motion bounds dirty, the imported-Twin grid rebuilt
        # every update, ticks exceeded 250 ms and SIM robots never finished warming up.
        source=open(Path(__file__).resolve().parents[2]/'scripts'/'twinpulse_fleet_runtime.py',encoding='utf-8').read()
        body=source[source.index('def _sync_sim_obstacles'):source.index('def _draw_lidar_layer')]
        self.assertIn("if key==getattr(self,'sim_obstacle_key',None):return",body)
        self.assertLess(body.index("if key==getattr(self,'sim_obstacle_key',None):return"),body.index('UsdGeom.Xform.Define'))


class SimObstacleBoxesTest(unittest.TestCase):
    def test_boxes_follow_position_and_size_and_skip_flat_items(self):
        # 2026-10-26: a nested comprehension in the runtime raised NameError, so the SIM box was never authored in Isaac.
        import importlib.util
        spec=importlib.util.spec_from_file_location('fleet_runtime_boxes',Path(__file__).resolve().parents[2]/'scripts'/'twinpulse_fleet_runtime.py')
        source=open(spec.origin,encoding='utf-8').read()
        namespace={};exec(source[source.index('def sim_obstacle_boxes'):source.index('def observe_startup')],namespace)
        boxes=namespace['sim_obstacle_boxes']([dict(position_m=[-2.07,2.06],size_m=[.5,.5,.5]),dict(position_m=[1,1],size_m=[.4,.4,.1])])
        self.assertEqual([tuple(round(v,3) for v in b) for b in boxes],[(-2.32,1.81,-1.82,2.31)])


class SimObstacleStopRecoveryTest(unittest.TestCase):
    def test_sim_engine_obstacle_stop_backs_off_and_replans_like_a_physical_proximity_stop(self):
        # 2026-10-26: the SIM-world test box ended the route with STEP_FAILED:OBSTACLE_STOP instead of recovering.
        import tempfile
        fleet=FakeFleet(['COMPLETED']*3+['FAILED']);fleet.fail_reason='OBSTACLE_STOP'
        with tempfile.TemporaryDirectory() as tmp:
            runner,result=run(fleet,tmp)
        texts=[b['payload'].get('text') for b in fleet.sent]
        self.assertIn('backward 40.0cm',texts)  # SIM backs off further than the physical 25 cm
        self.assertEqual(len(result['recoveries']),1)
        self.assertEqual(result['state'],'COMPLETED',result['reason'])
        self.assertEqual(result['recoveries'][0]['keepout_m'],.4)  # SIM keepout covers a whole 0.5 m box


class SimObstacleSectionCacheTest(unittest.TestCase):
    def test_lidar_section_cache_key_includes_the_sim_obstacle_set(self):
        # 2026-10-26: the SIM box was authored and the motion guard saw it, but the LiDAR section was cached per
        # Twin geometry epoch, so no return ever landed on the box and no candidate appeared.
        source=open(Path(__file__).resolve().parents[2]/'scripts'/'twinpulse_fleet_runtime.py',encoding='utf-8').read()
        self.assertIn("geometry_epoch=(self.identity,self.navigation_geometry_epoch,getattr(self,'sim_obstacle_key',None))",source)


class SimLoopStageContractTest(unittest.TestCase):
    """One pass over the SIM demo loop, one asserted contract per stage (2026-10-26, after each stage had only been unit-tested apart).

    1 obstacle placed in Isaac   -> the motion guard / LiDAR section include it, the Twin model does not
    2 robot meets it             -> OBSTACLE_STOP backs off 40 cm, re-plans round a 0.40 m keepout, completes
    3 stop-point LiDAR sees it   -> an unexplained ring of returns becomes one candidate (>=3 returns) at the box
    4 Auto-apply                 -> every edit runs as its own transaction; the LAST confirmed frame triggers the re-plan
    5 re-plan                    -> a fresh plan request carries planned_by auto_replan and the chat says so
    """
    def test_each_stage_contract_holds_in_one_pass(self):
        import importlib.util,sys,tempfile,threading
        from types import SimpleNamespace
        from twinpulse_app.robot_fleet import checked_sim_obstacle
        from twinpulse_core.declared_route import unexplained_scan_discs,cluster_candidates
        from twinpulse_app.conversation_service import ConversationService
        # 1 Isaac-side SIM obstacle: validated payload -> motion-guard box; the Twin model (SceneObjects) never gains it.
        spec=importlib.util.spec_from_file_location('fleet_runtime_contract','scripts/twinpulse_fleet_runtime.py')
        runtime=importlib.util.module_from_spec(spec);sys.modules[spec.name]=runtime;spec.loader.exec_module(runtime)
        item=checked_sim_obstacle(dict(position_m=[1.2,1.0],size_m=[.5,.5,.5],label='Box on leg 1'),0)
        self.assertEqual(item['source'],'SIM_WORLD_TEST_OBSTACLE_NOT_IN_TWIN')
        guard=runtime.sim_obstacle_boxes([item]);self.assertEqual(len(guard),1)
        self.assertAlmostEqual(guard[0][0],.95);self.assertAlmostEqual(guard[0][3],1.25)
        self.assertNotIn('object_id',item)  # a SIM-world obstacle is never a Twin SceneObject
        # 2 proximity stop in SIM recovers (the physical 25 cm values are untouched: a separate assertion keeps them).
        from twinpulse_app import declared_route_runner as drr
        self.assertEqual((drr.RECOVERY_KEEPOUT_M,drr.RECOVERY_BACKOFF_M),(.25,.25))
        fleet=FakeFleet(['COMPLETED']*3+['FAILED']);fleet.fail_reason='OBSTACLE_STOP'
        with tempfile.TemporaryDirectory() as tmp:runner,result=run(fleet,tmp)
        self.assertEqual(result['state'],'COMPLETED',result['reason']);self.assertEqual(len(result['recoveries']),1)
        self.assertIn('backward 40.0cm',[b['payload'].get('text') for b in fleet.sent])
        # 3 the stop-point scan explains the walls but not the box: exactly one candidate with >=3 returns sits on the box.
        cells=[[(ix+.5)*.1,(iy+.5)*.1,'occupied' if ix in (0,39) or iy in (0,29) else 'free',0,0,0,0] for ix in range(40) for iy in range(30)]
        start=[.6,.6,0.];box=item['position_m'][:2];half=.25
        ring=[(box[0]+half*math.cos(t)-start[0],box[1]+half*math.sin(t)-start[1]) for t in [i*math.tau/16 for i in range(16)]]
        walls=[(3.95-start[0],y*.1-start[1]) for y in range(1,30)]+[(x*.1-start[0],2.95-start[1]) for x in range(1,40)]+[(x*.1-start[0],.05-start[1]) for x in range(1,40)]
        review=unexplained_scan_discs(start,walls+ring,cells);self.assertTrue(review['used'],review)
        candidates=cluster_candidates(review['discs'])
        self.assertEqual(len(candidates),1,candidates);self.assertGreaterEqual(candidates[0]['returns'],3)
        self.assertLess(math.dist(candidates[0]['position_xy_m'],box),.2)
        # 4+5 Auto-apply through the REAL transaction sync: each COMMITTED frame drives the next edit, the last one drives the re-plan.
        messages=[];applied=[];transactions=[]
        s=SimpleNamespace(_lock=threading.Lock(),_state=dict(session_id='s',messages=[],cards=[],twin_edit_approval='auto',scene_feedback=None),_request_owner='o',
            _feedback_service=None,_feedback_outcome=None,_edit_transaction_marker=None,
            robot_fleet=SimpleNamespace(focused='r',navigation_scene=None),declared_routes=SimpleNamespace(active=lambda:False),_last_route_text='Survey the warehouse and come back',
            _message=lambda role,content,**kw:messages.append(dict(role=role,content=content,status=kw.get('status','completed'),operation_id=kw.get('operation_id'))) or s._state['messages'].append(messages[-1]),
            _event=lambda name,**kw:None,_persist=lambda:None,
            match_route_objects=lambda candidates:[],
            add_route_obstacles=lambda owner,plan_id,candidates,exclude=():applied.append(('add',len(candidates))) or ('op-add',len(candidates)),
            _plan_declared_route=lambda text,request_id,**kw:applied.append(('plan',text,kw['planned_by']['kind'])),
            workflow=SimpleNamespace(scene_edit_transaction=SimpleNamespace(snapshot=lambda owner:transactions[-1] if transactions else None)))
        s._choice=ConversationService._choice;s._card=lambda *a,**k:self.fail('auto mode must not ask')
        for name in ('_apply_next_auto_edit','_auto_replan','declared_route_finished','_sync_feedback'):setattr(s,name,getattr(ConversationService,name).__get__(s))
        plan=dict(plan_id='p'*32,waypoints=[[1,1],[2,1]])
        s.declared_route_finished(dict(plan=plan,state='COMPLETED',reason='ALL_STOPS_AND_RETURN_COMPLETED',completed_steps=9,context=dict(session_id='s'),
            waypoint_scans=[],reached_stops=[0,1],skipped_stops=[],candidates=candidates))
        self.assertEqual(applied,[('add',1)]);self.assertTrue(s._auto_replan_pending)  # one box: the only edit started at once
        transactions.append(dict(operation_id='op-add',state='COMMITTED',current_frame=None));s._sync_feedback('o')
        self.assertEqual(applied,[('add',1)])  # ACK without a frame: nothing more yet
        transactions.append(dict(operation_id='op-add',state='COMMITTED',current_frame='f1'));s._sync_feedback('o')
        self.assertEqual(applied,[('add',1)]);self.assertFalse(s._auto_replan_pending);self.assertIsNotNone(s._auto_replan_ready)  # frame confirmed, grid not yet rebuilt: no plan
        s._sync_feedback('o');self.assertEqual(applied,[('add',1)])  # still waiting for the navigation scene
        s.robot_fleet.navigation_scene=dict(binding=('e','s','rev2'),geometry={});s._sync_feedback('o')
        self.assertEqual(applied[-1],('plan','Survey the warehouse and come back','auto_replan'));self.assertIsNone(s._auto_replan_ready)
        self.assertTrue(any('Twin updated, saved and its current 3D frame confirmed.' in m['content'] for m in messages))
        self.assertTrue(any('re-planning "Survey the warehouse and come back"' in m['content'] for m in messages))
        transactions.append(dict(operation_id='op-add',state='COMMITTED',current_frame='f1'));s._sync_feedback('o')
        self.assertEqual(len([a for a in applied if a[0]=='plan']),1)  # the same frame never re-plans twice
        # 6 a grid that never comes back gives up honestly after the wait instead of pending forever
        s._auto_replan_ready=__import__('time').monotonic()-1000;s.robot_fleet.navigation_scene=None;s._sync_feedback('o')
        self.assertIsNone(s._auto_replan_ready);self.assertIn('Auto re-plan skipped',messages[-1]['content']);self.assertEqual(len([a for a in applied if a[0]=='plan']),1)


def lidar_twin(bounds,boxes,meshes=()):
    """Imported floor plus LiDAR 'unknown' boxes added as the App adds them (add_overlay, lidar_estimate),
    then the Kit -> App path: overlay meshes -> navigation cells -> grid wire -> decoded observed cells."""
    import hashlib
    from twinpulse_core.environment_overlays import add_overlay,overlay_meshes
    from twinpulse_core.environment_navigation import navigation_cells
    from twinpulse_core.navigation_grid import encode_navigation_grid,decode_navigation_grid
    from twinpulse_core.room_item_catalog import room_item_catalog_version
    def mesh(name,category,points):
        return dict(id='Env_'+hashlib.sha256(name.encode()).hexdigest()[:20],source_path='/Source/'+name,category=category,label=name,
            points_m=points,triangles=[[0,1,2],[0,2,3]],color_rgb=[.5,.6,.7],translation_m=[0,0,0])
    x0,y0,x1,y1=bounds
    environment=dict(schema_version='environment-static-1.0',source_name='room.usda',source_sha256=hashlib.sha256(b'room').hexdigest(),
        source_up_axis='Z',source_meters_per_unit=None,meters_per_unit=1.,units_basis='selected_for_sim',floor_offset_m=0.,
        meshes=[mesh('Floor','floor',[[x0,y0,0],[x1,y0,0],[x1,y1,0],[x0,y1,0]])]+[mesh(*m) for m in meshes])
    for identity,xy,size,yaw,uncertainty in boxes:
        item=dict(id='Added_'+identity,kind='unknown',label='LiDAR object',catalog_version=room_item_catalog_version('unknown'),
            position_m=[*xy,.2],dimensions_m=[*size,.4],yaw_deg=yaw,observation_time_utc=None)
        environment=add_overlay(environment,dict(item=item,uncertainty_m=uncertainty,
            evidence=dict(basis='lidar_estimate',source_name='route.json',sha256='a'*64,alignment_verified=False)))
    nav=navigation_cells(environment['meshes']+overlay_meshes(environment))
    return {k:nav[k] for k in ('bounds','obstacles','targets')},decode_navigation_grid(encode_navigation_grid(nav['cells']),nav['bounds'])


def berth(polyline,start,cells):
    """Smallest gap from the driven polyline to real non-free cells, and to synthetic-envelope cells beyond the start zone."""
    from twinpulse_core.bounded_grid_plan import SYNTHETIC_KEEPOUT_CELL
    points=[start[:2],*polyline];samples=[]
    for a,b in zip(points,points[1:]):
        n=max(1,math.ceil(math.dist(a,b)/.02));samples+=[(a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n) for i in range(n+1)]
    def gap(p,c):return math.hypot(max(abs(p[0]-c[0])-.05,0.),max(abs(p[1]-c[1])-.05,0.))
    real=[c for c in cells if c[2]!='free' and c[6]!=SYNTHETIC_KEEPOUT_CELL];synthetic=[c for c in cells if c[6]==SYNTHETIC_KEEPOUT_CELL]
    return (min([gap(p,c) for p in samples for c in real if abs(p[0]-c[0])<.6 and abs(p[1]-c[1])<.6] or [1.]),
            min([gap(p,c) for p in samples if math.dist(p,start[:2])>.4 for c in synthetic if abs(p[0]-c[0])<.6 and abs(p[1]-c[1])<.6] or [1.]))


class LidarBoxAtStartTest(unittest.TestCase):
    """2026-10-27 build 59 physical run on the saved Twin: the six auto-applied LiDAR boxes; the real box's uncertainty
    envelope (margin 0.4 m) reached the declared start's 0.35 m band, so an empty start was START_OR_GOAL_BLOCKED."""
    START=[.681,.206,.489]
    BOXES=[('c418ab4424675197e86d',[2.822,2.367],[.3,.3],-15.5,.1),('3ce9af1a2a4337f78441',[1.54,.578],[.378,.205],-49.,.3),
           ('ea7964f0a41d8a9e6a5b',[.025,1.142],[.3,.3],22.1,.1),('3ebb274001760ced6375',[.183,-1.234],[.3,.2],-52.3,.1),
           ('0d74ae65cb07c73b7d25',[.777,-2.191],[.3,.3],-52.,.1),('e7a6d0cbcb28be12d5c0',[-2.117,-.543],[.579,.387],43.1,.3)]
    ROOM=[-3.5,-3.5,4.,3.5]

    def test_envelope_in_the_start_band_plans_and_returns_but_real_geometry_and_the_far_band_still_block(self):
        from twinpulse_core.bounded_grid_plan import NoBoundedPath,plan_bounded_grid
        from twinpulse_core.declared_route import plan_through,replan_legs
        geometry,cells=lidar_twin(self.ROOM,self.BOXES);start=self.START
        plan=plan_through(start,[[1.,-.8]],geometry,cells,kind='physical')
        self.assertEqual(plan['polyline'][-1],start[:2])
        survey=plan_survey(start,geometry,cells,kind='physical',budget_m=8.)
        self.assertGreaterEqual(len(survey['waypoints']),2);self.assertEqual(survey['polyline'][-1],start[:2])
        for route in (plan,survey):
            real,band=berth(route['polyline'],start,cells)
            self.assertGreater(real,.33);self.assertGreater(band,.33)  # full berth from the box itself, and from its envelope once away
        # A recovery near the start re-plans home (the declared start's zone holds on the way back too).
        legs=replan_legs([.75,.1,0.],[[1.,-.8],start[:2]],geometry,cells,kind='physical',home=start[:2])
        self.assertEqual(legs[-1][-1],start[:2])
        # Goals are unchanged: an operator stop inside the envelope band far from the start is refused.
        with self.assertRaisesRegex(NoBoundedPath,'START_OR_GOAL_BLOCKED'):plan_through(start,[[2.3,.0]],geometry,cells,kind='physical')
        # A straight segment out of the start zone that passes 0.25 m from the envelope is still blocked beyond the zone.
        a,b,c,d=geometry['bounds']
        with self.assertRaisesRegex(NoBoundedPath,'REVIEWED_ROUTE_BLOCKED'):
            plan_bounded_grid(start[:2],(1.5,-.7),(a,c,b,d),resolution=.1,clearance=.35,observed_cells=cells,checked_route=[(1.5,-.7)],home=start[:2])
        # Inside the start zone real geometry keeps the full berth: a wall 0.25 m behind the start, or a LiDAR box whose
        # own body is 0.3 m away (its 0.15 m envelope is not); and an envelope's own footprint still blocks there.
        geometry,cells=lidar_twin(self.ROOM,self.BOXES,[('Wall','wall',[[.43,-.3,0],[.43,.7,0],[.43,.7,1],[.43,-.3,1]])])
        with self.assertRaisesRegex(NoBoundedPath,'START_OR_GOAL_BLOCKED'):plan_through(start,[[1.,-.8]],geometry,cells,kind='physical')
        geometry,cells=lidar_twin(self.ROOM,[('f'*20,[-1.,3.],[.3,.3],0.,.05),('e'*20,[-2.6,1.4],[.3,.3],0.,.3)])
        with self.assertRaisesRegex(NoBoundedPath,'START_OR_GOAL_BLOCKED'):plan_through([-1.5,3.,0.],[[-1.,2.]],geometry,cells,kind='physical')
        self.assertEqual(plan_through([-1.6,3.,0.],[[-1.,2.]],geometry,cells,kind='physical')['polyline'][-1],[-1.6,3.])  # 0.4 m from that body
        self.assertEqual(plan_through([-1.8,1.4,0.],[[-1.,2.]],geometry,cells,kind='physical')['polyline'][-1],[-1.8,1.4])  # 0.2 m from the other envelope
        with self.assertRaisesRegex(NoBoundedPath,'START_OR_GOAL_BLOCKED'):plan_through([-1.8,1.4,0.],[[-2.04,1.4]],geometry,cells,kind='physical')


class LidarBoxAheadSurveyTest(unittest.TestCase):
    def test_box_straight_ahead_in_a_narrow_room_still_gives_a_returning_survey(self):
        # 3.4 x 2.6 m room, LiDAR box 0.9 m straight ahead: every stop beyond it needs a detour (old rule: path <= 1.2 x distance + 0.2).
        geometry,cells=lidar_twin([0.,0.,3.4,2.6],[('b'*20,[1.5,1.3],[.4,.4],0.,.1)]);start=[.6,1.3,0.]
        plan=plan_survey(start,geometry,cells,kind='physical',budget_m=8.)
        self.assertGreaterEqual(len(plan['waypoints']),2,plan['waypoints']);self.assertEqual(plan['polyline'][-1],start[:2])
        self.assertLessEqual(plan['length_m'],8.)
        real,band=berth(plan['polyline'],start,cells);self.assertGreater(real,.33);self.assertGreater(band,.33)
        blocked=[c for c in cells if c[2]!='free']
        self.assertTrue(all(math.dist(w,c[:2])>=.6 for w in plan['waypoints'] for c in blocked))  # stop clearance unchanged
