# SPDX-License-Identifier: Apache-2.0
"""Route-end carry-over and the frame-bound declared start (2026-10-27 build 59 physical run).

After ALL_STOPS_AND_RETURN_COMPLETED, Twin-edit auto-apply added the LiDAR box (a new scene revision)
and the auto re-plan was refused: the declared start was bound to the content revision and was already
used. Real RobotFleet, CommandBroker scene lineage and DeclaredRouteRunner; only the robot session is
a double (wheel odometry + a LiDAR ring ray-cast in the room).
"""
from copy import deepcopy
import math
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from uuid import uuid4

from tests.integration import test_r5_product_api  # noqa: F401  (adds package source paths)
from tests.integration import test_physical_fleet_adapter as adapter_fixtures
from twinpulse_app.command_broker import BrokerError, CommandBroker
from twinpulse_app.declared_route_runner import DeclaredRouteRunner
from twinpulse_app.robot_fleet import RobotFleet

ROOM=dict(bounds=[0.,0.,4.,3.],obstacles=[[2.6,2.2,3.9,2.9]],targets=[])
BOX=[2.9,.6,3.3,1.]  # a real box the Twin lacks until the LiDAR edit adds it
START=[.8,.8,0.]
STOPS=[[1.6,1.2]]


def cells(obstacles):
    def blocked(x,y):return x<.1 or x>3.9 or y<.1 or y>2.9 or any(a<=x<=c and b<=y<=d for a,b,c,d in obstacles)
    return [[(ix+.5)*.1,(iy+.5)*.1,'occupied' if blocked((ix+.5)*.1,(iy+.5)*.1) else 'free',0,0,0,0] for ix in range(40) for iy in range(30)]


def ring(pose,boxes):
    """Sensor-frame returns of a 1-degree LiDAR at pose in the room (walls + boxes)."""
    segments=[((0,0),(4,0)),((4,0),(4,3)),((4,3),(0,3)),((0,3),(0,0))]
    for a,b,c,d in boxes:segments+=[((a,b),(c,b)),((c,b),(c,d)),((c,d),(a,d)),((a,d),(a,b))]
    points=[]
    for i in range(360):
        bearing=math.radians(i);dx,dy=math.cos(pose[2]+bearing),math.sin(pose[2]+bearing);best=None
        for (x1,y1),(x2,y2) in segments:
            ex,ey=x2-x1,y2-y1;den=dx*ey-dy*ex
            if abs(den)<1e-12:continue
            t=((x1-pose[0])*ey-(y1-pose[1])*ex)/den;u=((x1-pose[0])*dy-(y1-pose[1])*dx)/den
            if t>1e-6 and 0<=u<=1 and (best is None or t<best):best=t
        if best is not None and best<=3.5:points.append([round(best*math.cos(bearing),4),round(best*math.sin(bearing),4)])
    return points


class Twin:
    """Real CommandBroker scene registry: an import, then Twin edits whose parent is the previous revision."""
    def __init__(self):
        self.broker=CommandBroker(project_id='project-a')
        self.engine=dict(engine_connected=True,engine_session_id='engine',stage_epoch='stage',snapshot=dict(applied_revision=None))
        self.obstacles=list(ROOM['obstacles'])
        self.imported('home.usda')

    def environment(self,name,extra=()):
        from twinpulse_app.twin_export import generated_twin_usda, generated_twin_environment
        from twinpulse_core.models import SceneObject, Transform, ShapeSpec
        objects=[SceneObject('floor','floor',Transform((2.,1.5,-.05)),ShapeSpec('box',(4.,3.,.1))),
            SceneObject('wall_s','wall',Transform((2.,-.04,1.)),ShapeSpec('box',(4.,.08,2.))),
            SceneObject('sofa','rack',Transform((3.25,2.55,.4)),ShapeSpec('box',(1.3,.7,.8))),*extra]
        usda=generated_twin_usda(objects,scene_id='home').encode('utf-8')
        return generated_twin_environment(objects,usda,source_name=name,scene_id='home')

    def register(self,environment,parent):
        from twinpulse_core.environment_source import environment_objects
        from twinpulse_core.site_contracts import SceneRevision
        scene=SceneRevision(id='imported_space',objects=tuple(environment_objects(environment)),source='scan',
            source_ref='a'*64,parent_revision=parent,environment=environment)
        self.broker.register_site_scene('site-'+scene.revision[:24],scene)
        self.scene=scene;self.engine['snapshot']['applied_revision']=scene.revision
        return scene.revision

    def imported(self,name,extra=()):
        self.obstacles=list(ROOM['obstacles']);return self.register(self.environment(name,extra),None)

    def lidar_box(self,box=BOX):
        """What Twin-edit auto-apply does with a route candidate: one overlay, parent = the current revision."""
        from twinpulse_core.environment_overlays import add_overlay
        from twinpulse_core.room_item_catalog import room_item_catalog_version
        a,b,c,d=box
        item=dict(id='Added_'+uuid4().hex[:20],kind='unknown',label='LiDAR unknown #1 (route scan outline)',catalog_version=room_item_catalog_version('unknown'),
            position_m=[(a+c)/2,(b+d)/2,.2],dimensions_m=[c-a,d-b,.4],yaw_deg=0.,observation_time_utc=None,display_color=[.16,.16,.17])
        environment=add_overlay(self.scene.environment,dict(item=item,uncertainty_m=.3,
            evidence=dict(basis='lidar_estimate',alignment_verified=False,source_name='route.json',sha256='b'*64)))
        self.obstacles=self.obstacles+[list(box)]
        return self.register(environment,self.scene.revision)


class Robot:
    """Physical session double: finite commands move the body, wheel odometry reports it in its own frame."""
    def __init__(self,identity):
        self.identity=identity;self.lock=threading.Lock()
        self.connection=uuid4().hex;self.motion=uuid4().hex;self.boot='boot-1'
        self.body=list(START);self.odom=[2.,-1.,.3]  # odom frame differs from the Twin frame
        self.command=None;self.sequence=1;self.received=time.monotonic();self.boxes=[ROOM['obstacles'][0],BOX];self.on_drive=None;self.drives=0

    def snapshot(self,owner=None):
        with self.lock:
            x,y,yaw=self.odom
            return dict(robots=[dict(robot_id=self.identity,label='Burger',kind='physical',connection_epoch=self.connection,motion_epoch=self.motion,
                applied_motion_epoch=self.motion,connection_state='CONNECTED',live_heartbeat=True,control_state='READY',reason=None,
                pose=dict(x=x,y=y,yaw=yaw,position_m=[x,y,0.],yaw_rad=yaw,aligned=False,frame_id='odom',source='wheel_odom',independent_body=False),
                command=deepcopy(self.command),lidar_state='STREAMING',
                scan=dict(points=ring(self.body,self.boxes),stream_id='lidar-1',frame_sequence=self.sequence,raw_sha256='%064x'%self.sequence),
                scan_receipt=dict(age_ms=(time.monotonic()-self.received)*1000,age_basis='pc_scan_receipt',frame_id='native_sensor',aligned=False),
                capabilities=dict(read_only_connection=True,prepare=True,qualify=True,profile=True,lidar=True,drive=True),
                field=dict(mode='SUPERVISED_FIELD_TEST',armed=True,blockers=[],tracking=dict(status='INCONCLUSIVE',epoch=uuid4().hex,pose=None)),
                operation_id='o'*32,project_id='project-a',device_boot_id=self.boot,owned=True)])

    def drive(self,identity,owner,*,action,payload,request_id,connection_epoch,motion_epoch,request_twin_context,**kw):
        with self.lock:
            if (connection_epoch,motion_epoch)!=(self.connection,self.motion):raise BrokerError('fleet_motion_epoch_changed','Stale epoch.',status=409)
            sign=1 if payload['direction'] in ('forward','left') else -1
            if payload['direction'] in ('forward','backward'):
                for pose in (self.body,self.odom):pose[0]+=sign*payload['amount']*math.cos(pose[2]);pose[1]+=sign*payload['amount']*math.sin(pose[2])
            else:
                for pose in (self.body,self.odom):pose[2]=math.remainder(pose[2]+sign*payload['amount'],math.tau)
            # The completion's zero/readback rotates the motion epoch (2026-10-25).
            self.motion=uuid4().hex;self.sequence+=1;self.received=time.monotonic();self.drives+=1
            self.command=dict(request_id=request_id,text=payload['text'],kind='finite',state='COMPLETED',reason='TASK_COMPLETED')
        if self.on_drive:self.on_drive(self.drives)

    def stop(self,identity,owner,*,request_id=None,request_twin_context=None):
        with self.lock:self.motion=uuid4().hex;self.sequence+=1;self.received=time.monotonic()

    def tick(self):
        with self.lock:self.sequence+=1;self.received=time.monotonic()  # the LiDAR keeps streaming while the robot stands still

    def focus(self,identity,owner):pass
    def release_manual(self,identity,owner):pass
    def profile_for_view(self,identity):return None
    def field_config_for_view(self,identity):return None


class Chat:
    """The ConversationService route methods on a minimal state (route card, finish message, auto-apply, auto re-plan)."""
    def __init__(self,runner,fleet,twin,on_edit):
        from twinpulse_app.conversation_service import ConversationService as C
        self.s=s=SimpleNamespace(_lock=threading.RLock(),_state=dict(session_id='s',messages=[],cards=[],twin_edit_approval='auto'),
            robot_fleet=fleet,declared_routes=runner,_request_owner='owner',_external_started=False,messages=[],
            match_route_objects=None,move_route_object=None)
        s._message=lambda role,content,**kw:s.messages.append(content)
        s._event=lambda name,**kw:None;s._persist=lambda:None
        s._choice=C._choice;s._carried_start_text=lambda *args:C._carried_start_text(*args)
        def card(kind,question,choices,**kw):
            value=dict(id=uuid4().hex,kind=kind,question=question,choices=choices,state='waiting');s._state['cards'].append(value);return value
        s._card=card
        for name in ('_plan_declared_route','_route_preview','_answer_declared_route','declared_route_finished','_apply_next_auto_edit','_auto_replan'):
            setattr(s,name,getattr(C,name).__get__(s))
        def add_route_obstacles(owner,plan_id,candidates,*,exclude=()):
            on_edit();return 'edit-'+plan_id[:8],1
        s.add_route_obstacles=add_route_obstacles

    def card(self):
        return next(c for c in reversed(self.s._state['cards']) if c['kind']=='declared_route_run' and c['state']=='waiting')

    def run(self,card):
        self.s._answer_declared_route(card,next(c for c in card['choices'] if c['id']=='run'))


class RouteEndCarryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.twin=Twin();self.counter=0;self.results=[]
        self.registration=adapter_fixtures.PhysicalFleetAdapterTests.row('Burger','192.0.2.1');self.identity=self.registration['id']
        self.robot=Robot(self.identity);self.fleet=self.open_fleet()
        self.send('focus')
        self.declare(START)
        self.runner=self.open_runner()
        self.chat=Chat(self.runner,self.fleet,self.twin,self.apply_lidar_box)

    def open_fleet(self):
        registry=SimpleNamespace(registration_snapshot=lambda:dict(robots=[deepcopy(self.registration)]))
        devices=SimpleNamespace(registry_service=SimpleNamespace(registry=registry),physical_fleet=self.robot)
        broker=SimpleNamespace(project_id='project-a',supervisor_state=lambda:deepcopy(self.twin.engine),
            navigation_frame_lineage=lambda declared,current:self.twin.broker.navigation_frame_lineage(declared,current))
        fleet=RobotFleet(broker,Path(self.temp.name),devices=devices)
        self.addCleanup(fleet.close);self.show(fleet)
        return fleet

    def open_runner(self):
        clock=[0.]
        def sleep(s):clock[0]+=s;time.sleep(.0005)
        runner=DeclaredRouteRunner(self.fleet,self.temp.name,clock=lambda:clock[0],sleep=sleep,poll_s=1.,
            on_result=lambda result:(self.chat.s.declared_route_finished(result),self.results.append(result)))
        self.addCleanup(runner.cancel)
        return runner

    def show(self,fleet=None):
        """Kit reports the applied revision's navigation geometry."""
        (fleet or self.fleet).navigation_scene=dict(binding=('engine','stage',self.twin.engine['snapshot']['applied_revision']),
            geometry=dict(ROOM,obstacles=list(self.twin.obstacles)),produced_at=0.,observed_cells=cells(self.twin.obstacles))

    def apply_lidar_box(self):
        self.twin.lidar_box();self.show()

    def send(self,action,payload=None):
        self.counter+=1;row=next(r for r in self.fleet.snapshot()['robots'] if r['robot_id']==self.identity)
        return self.fleet.action(dict(action=action,request_id='request_%d'%self.counter,robot_id=self.identity,
            connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],payload=payload or {}),'owner')

    def declare(self,pose):
        self.send('set_twin_pose',dict(position_m=list(pose)))

    def route(self,text='Survey via (1.6, 1.2) and come back',stops=STOPS):
        self.chat.s._last_route_text=text
        self.chat.s._plan_declared_route(text,'request',stops=stops)
        return self.chat.card()

    def finish(self,card):
        count=len(self.results);self.chat.run(card)
        until=time.monotonic()+20
        while len(self.results)==count and time.monotonic()<until:time.sleep(.002)
        self.assertGreater(len(self.results),count,'the route did not finish')
        self.robot.tick()
        return self.results[-1]

    def refused(self,text):
        with self.assertRaises(BrokerError) as caught:self.runner.plan(self.identity)
        self.assertEqual(caught.exception.code,'declared_route_start_required')
        self.assertIn(text,str(caught.exception))

    def completed_then_auto_replanned(self):
        """Build-59 flow: declared start -> route -> COMPLETED -> LiDAR box auto-applied -> auto re-plan card."""
        first=self.finish(self.route())
        self.assertEqual(first['state'],'COMPLETED',first['reason'])
        revision=self.twin.engine['snapshot']['applied_revision']
        self.assertNotEqual(revision,first['plan']['scene_revision'],'auto-apply must have made a new Twin revision')
        self.chat.s._auto_replan()  # the edit's frame is confirmed (transaction sync)
        return first,self.replan_card(),self.chat.s._declared_route_pending

    def replan_card(self):
        self.assertTrue([c for c in self.chat.s._state['cards'] if c['kind']=='declared_route_run' and c['state']=='waiting'],
            'no re-plan card: '+self.chat.s.messages[-1])
        return self.chat.card()

    def test_completed_route_end_is_the_next_start_after_the_lidar_box_auto_apply(self):
        first,card,plan=self.completed_then_auto_replanned()
        # origin/main: "Set the robot position and heading on this Twin first." (scene revision changed, declaration used)
        self.assertEqual(plan['start_basis'],'route_end_odometry_estimate')
        self.assertEqual(plan['scene_revision'],self.twin.engine['snapshot']['applied_revision'])
        self.assertLess(math.dist(plan['start'][:2],first['end_pose_odometry'][:2]),.005)
        unc=first['end_estimate']['uncertainty']
        self.assertAlmostEqual(unc['position_m'],.025*first['end_estimate']['driven_m'],places=3)
        self.assertGreater(first['end_estimate']['driven_m'],1.5)
        self.assertIn('estimated end pose of the last route (carried start: declared start + wheel odometry, about ±%.0f cm'%(unc['position_m']*100),card['question'])
        self.assertIn('End pose estimate',' '.join(self.chat.s.messages))
        # The berth widens by the carried position bound plus its heading bound times the farthest planned point.
        reach=max(math.dist(plan['start'][:2],q) for q in plan['polyline'])
        self.assertGreater(plan['start_margin_m'],unc['position_m']+unc['yaw_rad']*reach-.001)
        self.assertAlmostEqual(plan['clearance_m'],.35+plan['start_margin_m'],places=6)
        self.assertIn('planned with a %.0f cm wider berth'%(plan['start_margin_m']*100),card['question'])
        view=next(r for r in self.fleet.snapshot()['robots'] if r['robot_id']==self.identity)['route_start_estimate']
        self.assertTrue(view['usable']);self.assertEqual(view['label'],'ROUTE_END_ESTIMATE_DECLARED_START_PLUS_WHEEL_ODOMETRY_NOT_LOCALIZED')
        second=self.finish(card)  # Run route on the re-plan card; nobody re-placed the robot
        self.assertEqual(second['state'],'COMPLETED',second['reason'])
        self.assertGreater(second['end_estimate']['uncertainty']['position_m'],unc['position_m'])  # chained drift accumulates
        self.assertEqual(self.runner.plan(self.identity)['start_basis'],'route_end_odometry_estimate')

    def test_re_plan_right_at_the_finish_uses_the_carried_start_but_not_a_stalled_lidar(self):
        # Every LiDAR candidate matches a Twin object: nothing to apply, so the re-plan runs inside the finish
        # callback, before the next LiDAR frame arrives.
        self.chat.s.match_route_objects=lambda candidates:[dict(candidate=i,aligned=True,label='sofa',distance_m=.05) for i in range(len(candidates))]
        first=self.finish(self.route())
        self.assertEqual(first['state'],'COMPLETED',first['reason'])
        self.assertEqual(first['plan']['scene_revision'],self.twin.engine['snapshot']['applied_revision'])  # no Twin edit
        card=self.replan_card()  # origin/main: "The robot has moved since this position was set."
        self.assertEqual(self.chat.s._declared_route_pending['start_basis'],'route_end_odometry_estimate')
        self.assertIn('carried start: declared start + wheel odometry',card['question'])
        with self.robot.lock:self.robot.sequence-=1;self.robot.received-=2.  # LiDAR stalled on the route end's frame for 2 s
        self.refused('no new LiDAR scan to compare with the route end')

    def test_declared_start_survives_a_twin_object_edit_but_not_a_different_usd(self):
        self.apply_lidar_box()  # an object edit: same import, same frame
        plan=self.runner.plan(self.identity)  # origin/main: "Set the robot position and heading on this Twin first."
        self.assertEqual(plan['start_basis'],'operator_declared_display_pose');self.assertEqual(plan['start'],START)
        self.assertTrue(next(r for r in self.fleet.snapshot()['robots'] if r['robot_id']==self.identity)['display_pose_current'])
        self.twin.imported('other.usda');self.show()  # a different USD is a different frame
        self.refused('Set the robot position and heading on this Twin first.')
        self.assertFalse(next(r for r in self.fleet.snapshot()['robots'] if r['robot_id']==self.identity)['display_pose_current'])

    def test_reimport_after_the_route_refuses_the_carried_start(self):
        self.completed_then_auto_replanned()
        self.twin.imported('home.usda');self.show();self.fleet.twin_imported()  # Import space -> adopt, as the API reports it
        self.refused('Set the robot position and heading on this Twin first.')
        self.assertIsNone(next(r for r in self.fleet.snapshot()['robots'] if r['robot_id']==self.identity)['display_pose'])

    def test_stop_after_the_route_refuses_the_carried_start(self):
        self.completed_then_auto_replanned()
        self.send('stop')
        self.refused('Stop, manual drive, a focus change or Disconnect was used')

    def test_a_route_stopped_midway_leaves_no_carried_start(self):
        _,card,_=self.completed_then_auto_replanned()
        start=self.robot.drives;stopped=[]
        def stop(count):  # Stop on the robot card while step 2 of the carried route runs
            if count-start==2 and not stopped:stopped.append(1);threading.Thread(target=self.send,args=('stop',)).start()
        self.robot.on_drive=stop
        second=self.finish(card)
        self.assertTrue(stopped);self.assertEqual(second['state'],'CANCELLED',second['reason']);self.assertNotIn('end_estimate',second)
        self.assertNotIn(self.identity,self.runner.end_estimates)  # the run consumed the carried start
        self.refused('Set its position and heading on the Twin again.')

    def test_wheel_motion_after_the_route_refuses_the_carried_start(self):
        self.completed_then_auto_replanned()
        with self.robot.lock:
            for pose in (self.robot.body,self.robot.odom):pose[0]+=.1*math.cos(pose[2]);pose[1]+=.1*math.sin(pose[2])
        self.robot.tick()
        self.refused('the wheels moved 10 cm')

    def test_robot_carried_by_hand_after_the_route_refuses_the_carried_start(self):
        self.completed_then_auto_replanned()
        with self.robot.lock:self.robot.body[0]+=.25;self.robot.body[2]+=.1  # lifted and put down: wheels report nothing
        self.robot.tick()
        self.refused('the LiDAR view differs from the route end')

    def test_reconnect_after_the_route_refuses_the_carried_start(self):
        self.completed_then_auto_replanned()
        with self.robot.lock:self.robot.connection=uuid4().hex
        self.refused('the robot connection changed since the route ended')

    def test_manual_position_overrides_the_carried_start(self):
        self.completed_then_auto_replanned()
        self.declare([.9,.8,0.])
        self.assertEqual(self.runner.plan(self.identity)['start_basis'],'operator_declared_display_pose')
        view=next(r for r in self.fleet.snapshot()['robots'] if r['robot_id']==self.identity)['route_start_estimate']
        self.assertFalse(view['usable']);self.assertIn('set by hand',view['reason'])

    def test_route_beyond_the_drift_bound_is_not_carried(self):
        stops=[[3.3,1.7],[1.0,2.2],[3.3,1.5],[1.0,1.6]]
        first=self.finish(self.route('Survey via (3.3, 1.7), (1.0, 2.2), (3.3, 1.5), (1.0, 1.6) and come back',stops=stops))
        self.assertEqual(first['state'],'COMPLETED',first['reason'])
        self.assertTrue('end_estimate' in first,'the finished route reports no end pose estimate')
        self.assertGreater(first['end_estimate']['uncertainty']['position_m'],.18,first['end_estimate'])
        self.assertFalse(first['end_estimate']['carry_over'])
        self.refused('odometry uncertainty')

    def test_app_restart_refuses_the_used_manual_declaration(self):
        self.chat.s._state['twin_edit_approval']='review'  # no Twin edit: the same revision before and after the restart
        first=self.finish(self.route())
        self.assertEqual(first['state'],'COMPLETED',first['reason'])
        self.fleet.close();self.fleet=self.open_fleet();self.runner=self.open_runner()  # App restart: same robot-fleet.json
        # origin/main restores the used declaration and plans from a start the robot already left.
        self.refused('Set the robot position and heading on this Twin first.')
        self.declare(START)  # a new declaration is restored after a restart while unused
        self.fleet.close();self.fleet=self.open_fleet();self.runner=self.open_runner()
        self.assertEqual(self.runner.plan(self.identity)['start_basis'],'operator_declared_display_pose')


if __name__=='__main__':unittest.main()
