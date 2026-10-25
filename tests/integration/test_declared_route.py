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
        self.outcomes=list(outcomes);self.sent=[];self.curve=0.;self.fail_reason='X'
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
            else:yaw+=step['amount']*(1 if step['direction']=='left' else -1)
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
        self.assertIn('backward 25.0cm',texts)
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
