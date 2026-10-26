# SPDX-License-Identifier: Apache-2.0
"""Supplementary device-free task contracts; fake engine/model, not Isaac QA."""
from copy import deepcopy
from contextlib import contextmanager
import json
import math
from pathlib import Path
from threading import Event,Thread
from threading import RLock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from tests.integration import test_r5_product_api
from tests.integration.test_robot_fleet import Broker
from twinpulse_app.robot_fleet import RobotFleet
from twinpulse_app.robot_task_service import RobotTaskService,_OneCallLedger
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.robot_task_plan import VERSION,checked_plan,task_request,primitive_text
from twinpulse_core.robot_survey import next_observation,route_to,execution_cost,checked_motion_segment,MIN_CLEARANCE_M,PLANNING_CLEARANCE_M
from twinpulse_core import canonical_sha256
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.nebius_pipeline import ChatCompletion
import tempfile


def plan(steps=None):return dict(schema_version=VERSION,mode='plan',explanation='Bounded observation and return, not certified whole-room coverage.',
    limits=dict(distance_m=3.,duration_s=120.,segments=64),steps=steps if steps is not None else [dict(op='observe'),dict(op='survey'),dict(op='return_to_start'),dict(op='stop')])


class TaskSchemaTests(unittest.TestCase):
    def test_survey_does_not_authorize_model_invented_relative_waypoints(self):
        from twinpulse_core.robot_task_plan import request_capabilities,plan_schema
        invented=plan([dict(op='move_relative',direction='forward',amount=.5),dict(op='survey'),dict(op='return_to_start'),dict(op='stop')])
        for text in ('Measure the reachable room, return to the start and stop. Limit total travel to 2.5 metres.',
                     'Inspect the right wall and go back to start, then stop.',
                     '방 전체를 한바퀴 이동하며 라이다로 측정하고 돌아와. 총 2.5m 이내에서 정지.'):
            self.assertNotIn('move_relative',request_capabilities(text))
            with self.assertRaisesRegex(ValueError,'FIXED_MOVES_NOT_REQUESTED'):checked_plan(invented,request_text=text)
            schema=plan_schema(capabilities=request_capabilities(text))
            self.assertNotIn('move_relative',[s['properties']['op']['const'] for s in schema['properties']['steps']['items']['anyOf']])
            self.assertEqual(checked_plan(plan(),request_text=text)['steps'],plan()['steps'])
        for text in ('Move forward 10 centimetres, survey the room, return and stop.',
                     'Measure the room, turn left 30 degrees, return and stop.',
                     '전진 10cm 하고 방을 측정한 뒤 돌아와 멈춰'):
            self.assertIn('move_relative',request_capabilities(text))
            self.assertEqual(checked_plan(invented,request_text=text),invented)
    def test_sim_driver_envelope_cannot_be_lowered_by_requested_task_clearance(self):
        from twinpulse_core.robot_survey import task_clearance,SIM_EXECUTOR_REFERENCE_CLEARANCE_M
        self.assertEqual(task_clearance('physical'),.15)
        self.assertAlmostEqual(task_clearance('physical',planning=True),.17)
        self.assertAlmostEqual(task_clearance('sim'),.2075)
        self.assertAlmostEqual(task_clearance('sim',planning=True),.2275)
        from scripts.twinpulse_fleet_runtime import FleetRuntime,SIM_STOP_SKIN_M,SIM_STOP_SUBSTEP_TRAVEL_M
        boundary=[1.,task_clearance('sim'),0.];box=[0.,0.,2.,0.]
        self.assertAlmostEqual(FleetRuntime._gap(boundary,box),SIM_STOP_SKIN_M+SIM_STOP_SUBSTEP_TRAVEL_M)
        self.assertEqual(task_clearance('sim'),SIM_EXECUTOR_REFERENCE_CLEARANCE_M)
    def test_compositions_are_data_not_per_phrase_functions(self):
        for text in ('방 전체를 한바퀴 이동하며 라이다로 측정하고 돌아와','Measure the room and return','앞으로 20cm 간 다음 좌회전하고 돌아와','Explore then go to the chair'):
            self.assertTrue(task_request(text),text)
        for text in ('stop','Forward 10 cm','6m 방을 만들고 소파를 배치해줘','의자를 옮겨줘'):
            self.assertFalse(task_request(text),text)
    def test_in_place_is_robot_motion_not_the_scene_verb_place(self):
        # 2026-10-25: 'in-place' matched 'place' and sent survey requests to scene edit.
        from twinpulse_app.robot_fleet import parse_robot_command
        for text in ('Rotate in-place, survey the room and return','Turn in place then explore the room'):
            self.assertTrue(task_request(text,'physical'),text)
        self.assertEqual(parse_robot_command('Rotate in place 90 degrees left in this room')['direction'],'left')
        for text in ('Place a chair in the room','Create a room and place the sofa'):
            self.assertFalse(task_request(text),text)
            self.assertIsNone(parse_robot_command(text),text)
        self.assertEqual(checked_plan(plan())['steps'][1],{'op':'survey'})
        other=plan([dict(op='move_relative',direction='forward',amount=.2),dict(op='move_relative',direction='left',amount=math.pi/2),dict(op='stop')])
        self.assertIn('0.200000000 m',primitive_text(checked_plan(other)['steps'][0]))
    def test_no_code_authority_unsupported_or_unbounded_steps(self):
        for mutation in (lambda p:p.update(code='exec'),lambda p:p['steps'].append(dict(op='shell',command='x')),
                         lambda p:p['limits'].update(segments=129),lambda p:p['limits'].update(distance_m=float('nan')),
                         lambda p:p.update(steps=[dict(op='move_relative',direction='forward',amount=3)]),
                         lambda p:p.update(mode='clarify')):
            p=plan();mutation(p)
            with self.assertRaises(ValueError):checked_plan(p)
    def test_explanation_cannot_replace_requested_return_or_stop_steps(self):
        bad=plan([dict(op='move_relative',direction='forward',amount=.1),dict(op='move_relative',direction='left',amount=.523598)])
        bad['explanation']='Return to the start and stop.'
        with self.assertRaisesRegex(ValueError,'REQUESTED_CAPABILITY_MISSING'):
            checked_plan(bad,request_text='Move forward10cm, turn left30 degrees, then return to the start and stop.')
        bad['steps']+=[dict(op='return_to_start'),dict(op='stop')]
        self.assertEqual(len(checked_plan(bad,request_text='Move, return and stop')['steps']),4)
        bad['steps'].append(dict(op='move_relative',direction='forward',amount=.1))
        with self.assertRaisesRegex(ValueError,'RETURN_NOT_FINAL'):checked_plan(bad,request_text='Move, return and stop')
    def test_stop_survey_and_stop_now_never_wait_for_a_model(self):
        from twinpulse_app.robot_fleet import parse_robot_command
        for text in ('stop survey','Stop the current task','작업 취소해줘','탐색을 즉시 정지해'):
            self.assertFalse(task_request(text));self.assertEqual(parse_robot_command(text),{'action':'stop'})
    def test_unknown_cells_and_return_budget_not_silently_free(self):
        geometry=dict(bounds=[0,0,3,3],obstacles=[])
        with self.assertRaises(ValueError):route_to([1,1,0],[2,1],geometry,observed_cells=[])
        result=next_observation([1,1,0],[1,1,0],[[1,1,0]],geometry,.15,return_required=True)
        self.assertIsNone(result['route']);self.assertNotEqual(result['reason'],'KNOWN_LOCATIONS_VISITED')
        result=next_observation([1,1,0],[1,1,0],[[1,1,0]],geometry,3,return_required=True)
        self.assertIsNotNone(result['route']);self.assertGreater(result['reserved_return_m'],0)
    def test_one_dispatch_even_after_failed_unknown_outcome(self):
        ledger=_OneCallLedger(SimpleNamespace(state={},reserve=Mock(side_effect=OSError('disk'))))
        with self.assertRaises(OSError):ledger.reserve({})
        with self.assertRaisesRegex(ValueError,'ONE_CALL'):ledger.reserve({})
        self.assertEqual(ledger.ledger.reserve.call_count,1)
    def test_return_reservation_includes_turns_observations_and_segments(self):
        outward=execution_cost([1,1,0],[[.35,1]])
        back=execution_cost(outward['end_pose'],[[1,1]])
        self.assertGreater(outward['duration_s']+back['duration_s'],47)
        self.assertEqual(outward['segments']+back['segments'],6)
    def test_navigation_approach_uses_same_conservative_clearance_as_execution(self):
        from twinpulse_core.sim_fleet_navigation import approach_plan
        target=dict(id='bed',kind='bed',label='bed',bounds=[1.5,1,2.5,2])
        geometry=dict(bounds=[0,0,4,4],obstacles=[target['bounds']])
        result=approach_plan([.7,1.5,0],'bed',[target],geometry['bounds'],geometry['obstacles'],clearance_m=PLANNING_CLEARANCE_M)
        self.assertEqual(result['clearance_m'],PLANNING_CLEARANCE_M)
        self.assertIsNotNone(route_to([.7,1.5,0],result['goal_xy'],geometry))

    def test_user_selected_fifteen_centimetre_envelope_not_a_braking_override(self):
        self.assertEqual(MIN_CLEARANCE_M,.15)
        self.assertAlmostEqual(PLANNING_CLEARANCE_M,.17)
        geometry=dict(bounds=[0,0,3,3],obstacles=[[1.4,1.,1.6,1.2]])
        # Centre-to-obstacle envelope: 14.9cm is rejected, 15.1cm is clear.
        with self.assertRaises(ValueError):
            checked_motion_segment([1.,.851,0],'forward',1.,geometry)
        self.assertEqual(checked_motion_segment([1.,.849,0],'forward',1.,geometry),[2.,.849])
        # The 2cm nominal planning margin is stricter than dispatch, not an epsilon.
        with self.assertRaises(ValueError):route_to([1.5,.84,0],[1.7,.84],geometry)
        self.assertTrue(route_to([1.,.82,0],[2.,.82],geometry))
        from twinpulse_core.sim_fleet_navigation import approach_plan
        target=dict(id='bed',kind='bed',bounds=geometry['obstacles'][0])
        self.assertEqual(approach_plan([.7,.6,0],'bed',[target],geometry['bounds'],geometry['obstacles'])['clearance_m'],.25)
        with self.assertRaises(ValueError):
            approach_plan([.7,.6,0],'bed',[target],geometry['bounds'],geometry['obstacles'],clearance_m=.149)

    def test_tangent_waypoint_is_not_a_robust_task_goal_or_snapped_pose(self):
        geometry=dict(bounds=[0,0,3,3],obstacles=[])
        cells=[[(x+.5)*.1,(y+.5)*.1,'occupied' if (x,y)==(19,8) else 'free',0,0,0,0] for x in range(30) for y in range(30)]
        # Preserve the tangent regression at the new explicitly selected .15m
        # envelope. The original .30m incident artifacts remain unchanged.
        with self.assertRaisesRegex(ValueError,'START_OR_GOAL_BLOCKED'):
            checked_motion_segment([1.900000000091919,.6500000159354973,2.634397e-8],'forward',.05,geometry,observed_cells=cells)
        # The nominal .17m planner rejects a tangent .15m goal.
        with self.assertRaisesRegex(ValueError,'START_OR_GOAL_BLOCKED'):
            route_to([1.3,.65,0],[1.95,.65],geometry,observed_cells=cells)
        self.assertTrue(route_to([1.3,.60,0],[1.95,.60],geometry,observed_cells=cells))

    def test_actual_yaw_projection_and_unknown_cells_are_checked_before_dispatch(self):
        geometry=dict(bounds=[0,0,3,3],obstacles=[])
        cells=[[(x+.5)*.1,(y+.5)*.1,'occupied' if (x,y)==(19,8) else 'free',0,0,0,0] for x in range(30) for y in range(30)]
        # Ideal y=.65 is not the actual heading at the former .04 threshold.
        with self.assertRaises(ValueError):checked_motion_segment([1.7,.65,.0399],'forward',.2,geometry,observed_cells=cells)
        self.assertEqual(checked_motion_segment([1.7,.60,0],'forward',.2,geometry,observed_cells=cells),[1.9,.60])
        with self.assertRaises(ValueError):checked_motion_segment([1,1,0],'forward',.2,geometry,observed_cells=[])

    def test_small_route_turn_is_reserved_in_time_and_segments(self):
        yaw=.02;goal=[1+math.cos(yaw),1+math.sin(yaw)]
        cost=execution_cost([1,1,0],[goal])
        self.assertEqual(cost['segments'],4) # one small turn + three .4m moves
        self.assertGreater(cost['duration_s'],38)


class GeometryPersistenceFreshnessTests(unittest.TestCase):
    """Fake clock/storage only; not physical latency or installed UI evidence."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=10.;self.calls=0
        self.service=object.__new__(RobotTaskService)
        self.service.clock=lambda:self.now
        self.service.fleet=SimpleNamespace(lock=RLock(),navigation_scene=self.scene())
        self.service.binding=('robot','connection','operation',('engine','stage','revision'))
        self.service.root=Path(self.temp.name);self.service.job={'task_id':'a'*32}
        self.service.geometry_records=set();self.service._event=Mock()
        self.service._check=Mock(return_value={'kind':'sim','pose':{'position_m':[1,1,0]}})
        self.service._peer_context=Mock(return_value=[])
    def scene(self,epoch=1):
        return dict(binding=('engine','stage','revision'),produced_at=self.now,
            geometry=dict(epoch=epoch,bounds=[0,0,3,3],obstacles=[],targets=[]),observed_cells=[])
    def slow_save(self,*args):
        self.calls+=1;self.now+=.675
        self.service.fleet.navigation_scene=self.scene()
    def test_slow_first_record_uses_new_snapshot_not_retimed_old_source(self):
        original=self.service.fleet.navigation_scene
        with patch('twinpulse_app.robot_task_service.atomic_json',side_effect=self.slow_save):
            _,scene,_=self.service._geometry()
        self.assertEqual(self.calls,1);self.assertEqual(self.service._check.call_count,2)
        self.assertEqual(original['produced_at'],10.);self.assertEqual(scene['produced_at'],10.675)
    def test_absent_new_telemetry_still_expires(self):
        def stalled(*args):self.now+=.675
        with patch('twinpulse_app.robot_task_service.atomic_json',side_effect=stalled):
            with self.assertRaisesRegex(ValueError,'CURRENT_GEOMETRY_REQUIRED'):self.service._geometry()
        self.assertEqual(self.service._check.call_count,2)
    def test_changing_geometry_has_no_unbounded_retry(self):
        def changed(*args):
            self.slow_save();self.service.fleet.navigation_scene=self.scene(self.calls+1)
        with patch('twinpulse_app.robot_task_service.atomic_json',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'CURRENT_GEOMETRY_REQUIRED'):self.service._geometry()
        self.assertEqual(self.calls,2);self.assertEqual(self.service._check.call_count,2)
    def test_storage_error_and_stop_during_write_do_not_resume(self):
        with patch('twinpulse_app.robot_task_service.atomic_json',side_effect=OSError('storage failed')):
            with self.assertRaisesRegex(OSError,'storage failed'):self.service._geometry()
        self.assertFalse(self.service.geometry_records);self.service._check.reset_mock()
        self.service._check.side_effect=[{'kind':'sim'},BrokerError('cancelled','stopped',status=409)]
        with patch('twinpulse_app.robot_task_service.atomic_json',side_effect=self.slow_save):
            with self.assertRaisesRegex(BrokerError,'stopped'):self.service._geometry()
        self.assertEqual(self.service._check.call_count,2)
    def test_new_context_after_record_is_rejected(self):
        def rebound(*args):
            self.slow_save();self.service.fleet.navigation_scene['binding']=('engine','new-stage','revision')
        with patch('twinpulse_app.robot_task_service.atomic_json',side_effect=rebound):
            with self.assertRaisesRegex(ValueError,'CURRENT_GEOMETRY_REQUIRED'):self.service._geometry()
        self.assertEqual(self.calls,1)


class RobotTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();broker=Broker();broker._lock=RLock();broker.has_pending_operations=lambda:False
        self.fleet=RobotFleet(broker,Path(self.temp.name));self.index=0
        self.service=RobotTaskService(SimpleNamespace(),self.fleet,object())
        self.robot=self.send('register_sim',payload=dict(label='Task SIM',position_m=[1,1,0]))['focused_robot_id']
        self.send('connect');self.reporting=Event();self.reporting.set()
        self.engine=Thread(target=self.fake_engine,daemon=True);self.engine.start()
        self.wait(lambda:self.fleet.robots[self.robot]['connection_state']=='CONNECTED')
        self.send('prepare')
    def tearDown(self):
        self.service.close();self.reporting.clear();self.engine.join(2);self.fleet.close();self.temp.cleanup()
    def wait(self,predicate,seconds=5):
        end=time.monotonic()+seconds
        while not predicate():
            if time.monotonic()>end:raise AssertionError('supplementary wait expired')
            time.sleep(.01)
    def send(self,action,payload=None,token=None):
        self.index+=1
        return self.fleet.action(dict(action=action,request_id='test-'+str(self.index),robot_id=getattr(self,'robot',None),
            connection_epoch=None,motion_epoch=None,payload=payload or {}),'owner',_task_token=token)
    def fake_engine(self):
        while self.reporting.is_set():
            with self.fleet.lock:
                row=self.fleet.robots[self.robot];pose=deepcopy(row['pose']['position_m']);task=deepcopy(row['_task'])
                value=dict(robot_id=self.robot,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],sequence=row['telemetry_sequence']+1,
                    runtime_startup=dict(model_authored=True,render_observed=True,snapshot_capture_pending=False,post_author_updates=2,ready=True))
                if task:
                    start=task['start_pose'];direction=task['direction'];amount=task['amount'];pose=list(start)
                    if direction in {'forward','backward'}:
                        signed=amount*(1 if direction=='forward' else -1);pose[0]+=signed*math.cos(pose[2]);pose[1]+=signed*math.sin(pose[2])
                    else:pose[2]+=amount*(1 if direction=='left' else -1)
                    value.update(reason='TASK_COMPLETED',task_id=task['task_id'])
                value['position_m']=pose
                if row['lidar_state'] in {'STARTING','STREAMING'}:
                    value['scan']=dict(source='isaac_usd_surface_rays',points=[[1.5*math.cos(i*math.tau/120),1.5*math.sin(i*math.tau/120)] for i in range(120)],
                        captured_at_ms=time.time()*1000,position_m=[pose[0]-.032*math.cos(pose[2]),pose[1]-.032*math.sin(pose[2]),pose[2]],height_m=.182)
            self.fleet.engine_exchange('engine','stage',dict(engine_session_id='engine',stage_epoch='stage',report=dict(applied_revision='revision',robots=[value],
                produced_monotonic_s=time.monotonic(),scene_geometry=dict(epoch=1,targets=[],bounds=[0,0,3,3],obstacles=[]))))
            time.sleep(.01)
    def ready(self,p):
        identity='a'*32;row=self.fleet.robots[self.robot]
        self.service.owner='owner';self.service.cancelled=Event()
        self.service.job=dict(schema_version=VERSION,task_id=identity,request_id='fixture-plan',text='supplementary',project_id='test-project',robot_id=self.robot,robot_kind='sim',
            state='READY',reason=None,plan=p,plan_sha256=canonical_sha256(p),events=[],step_index=0,segments=0,distance_m=0.,coverage=None,
            proposal_binding=[self.robot,row['kind'],row['connection_epoch'],row['operation_id'],list(self.service._scene_binding())],
            source_state_sha256=canonical_sha256(self.service.source_binding()),
            physical_authority=False,whole_room_coverage_verified=False)
    def test_real_fleet_finite_sequence_requires_exact_new_applied_epoch(self):
        self.ready(plan([dict(op='observe'),dict(op='move_relative',direction='forward',amount=.2),dict(op='move_relative',direction='left',amount=1.),dict(op='stop')]))
        self.service.run('owner',self.service.job['plan_sha256'])
        self.wait(lambda:self.service.job['state'] in {'COMPLETED','FAILED'})
        self.assertEqual(self.service.job['state'],'COMPLETED',self.service.job)
        events=self.service.job['events'];children=[e for e in events if e['kind']=='child_completed']
        self.assertEqual(len(children),2)
        for event in children:self.assertEqual(event['new_motion_epoch'],event['applied_motion_epoch'])
        started=[e for e in events if e['kind']=='child_started']
        self.assertEqual(len(started),2)
        from twinpulse_core.robot_survey import task_clearance
        self.assertTrue(all(e['minimum_clearance_m']==task_clearance('sim') and e['requested_minimum_clearance_m']==MIN_CLEARANCE_M for e in started))
        self.assertGreater(self.service.job['measured_coverage']['observations'],0)
        self.assertFalse(self.service.job['measured_coverage']['model_prior_is_measurement'])
        self.assertTrue((self.service.root/('a'*32)/'task.json').exists())
    def test_stop_revokes_old_permit_before_next_child_even_if_epoch_refreshed(self):
        self.ready(plan());self.service.job['state']='RUNNING';permit=object();self.service.permit=permit
        self.send('stop');self.assertTrue(self.service.cancelled.is_set())
        row=self.fleet.robots[self.robot]
        with self.assertRaisesRegex(BrokerError,'stopped'):
            self.fleet.action(dict(action='command',request_id='old-task',robot_id=self.robot,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],payload=dict(text='forward .1 m')),'owner',_task_token=permit)
        self.assertIsNone(self.fleet.robots[self.robot]['_task'])
    def test_provider_boundary_is_one_text_only_proposal_not_motion(self):
        route={'fixture':'no-network'};provider=object.__new__(BudgetedPipeline)
        provider.policy=GenerationPolicy();provider.planner_model_id='supplementary-fake-planner'
        provider.route_sha256=canonical_sha256(route);provider.stage_output_token_caps={'planner':2000};provider.planner_template_no_thinking=False
        provider._transport=SimpleNamespace(record_validation=Mock());provider.diagnostic_for=Mock(return_value={'fixture':True})
        bodies=[]
        async def complete(stage,body,token,config):
            bodies.append(deepcopy(body));return ChatCompletion('fixture',provider.planner_model_id,json.dumps(plan()),'stop',{},'fixture-attempt')
        provider._complete_stage=complete
        with patch('twinpulse_app.stage_routing.build_configured_stage_service',return_value=SimpleNamespace(_provider=provider,_config=object())),patch('twinpulse_app.stage_routing.StageRoutingSettings',return_value=SimpleNamespace(load=lambda:route)):
            self.service.propose('Measure the room and return','owner','text-only')
            self.wait(lambda:self.service.job['state'] in {'READY','FAILED'})
        self.assertEqual(self.service.job['state'],'READY',self.service.job)
        self.assertEqual(len(bodies),1);sent=json.loads(bodies[0]['messages'][1]['content'])
        self.assertEqual(set(sent),{'text','robot_kind','capabilities','mandatory_capabilities'})
        self.assertEqual(sent['mandatory_capabilities'],['return_to_start','survey'])
        self.assertIsNone(self.fleet.robots[self.robot]['_task'])
        self.assertEqual(self.fleet.robots[self.robot]['lidar_state'],'OFF')
        with self.assertRaises(BrokerError):self.service.propose('retry','owner','text-only')
    def test_revoked_or_closed_task_can_still_stop(self):
        self.ready(plan());permit=object();self.service.permit=permit;self.service.closed=True
        self.service.revoke('close')
        self.send('stop',token=permit)
        self.assertEqual(self.fleet.robots[self.robot]['reason'],'OPERATOR_STOP')
    def test_unconfirmed_stop_keeps_execution_ownership_and_blocks_new_motion(self):
        self.ready(plan());self.service.job['state']='FAILED'
        row=self.fleet.robots[self.robot]
        self.service.pending_stop=dict(request_id='missing-stop',motion_epoch='not-applied',connection_epoch=row['connection_epoch'],operation_id=row['operation_id'])
        self.assertTrue(self.service.owns_execution());self.assertTrue(self.service.active())
        self.service.snapshot('owner');self.assertIsNotNone(self.service.pending_stop)
        with self.assertRaises(BrokerError):self.send('command',dict(text='forward .1 m'))
        self.assertIsNone(self.fleet.robots[self.robot]['_task'])
    def test_cancel_waits_for_admitted_publication_and_stops_it_before_ack(self):
        self.ready(plan());self.service.job['state']='RUNNING';permit=object();self.service.permit=permit
        entered=Event();release=Event();cancelled=Event();calls=0;original=self.fleet._task_admission;errors=[]
        def admission(body,token):
            nonlocal calls
            original(body,token)
            if token is permit and body['action']=='command':
                calls+=1
                if calls==2:entered.set();release.wait(3)
        row=self.fleet.robots[self.robot]
        body=dict(action='command',request_id='barrier-child',robot_id=self.robot,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],payload=dict(text='forward .2 m'))
        scene=self.fleet.navigation_scene
        self.service.motion_pin=dict(request_id=body['request_id'],text=body['payload']['text'],pose=deepcopy(row['pose']['position_m']),binding=scene['binding'],geometry=deepcopy(scene['geometry']),peers=[])
        def dispatch():
            try:self.fleet.action(body,'owner',_task_token=permit)
            except Exception as exc:errors.append(str(exc))
        def cancel():
            self.service.cancel('owner');cancelled.set()
        with patch.object(self.fleet,'_task_admission',side_effect=admission):
            child=Thread(target=dispatch);child.start();self.assertTrue(entered.wait(2))
            cancel_thread=Thread(target=cancel);cancel_thread.start()
            self.wait(lambda:self.service.cancelled.is_set());self.assertFalse(cancelled.is_set())
            release.set();child.join(3);cancel_thread.join(5)
        self.assertTrue(cancelled.is_set());self.assertIsNone(self.fleet.robots[self.robot]['_task'])
        self.assertEqual(self.fleet.robots[self.robot]['reason'],'OPERATOR_STOP')
        self.service.job['state']='CANCELLED'

    def test_checked_projection_cannot_survive_a_pose_or_map_change(self):
        self.ready(plan());self.service.job['state']='RUNNING';self.service.permit=object()
        row=self.fleet.robots[self.robot];scene=self.fleet.navigation_scene
        body=dict(request_id='checked',payload=dict(text='forward .2 m'))
        self.service.motion_pin=dict(request_id='checked',text='forward .2 m',pose=deepcopy(row['pose']['position_m']),binding=scene['binding'],geometry=deepcopy(scene['geometry']),peers=[])
        self.service.admit_motion(body,row,scene)
        changed=deepcopy(row);changed['pose']['position_m'][0]+=.001
        with self.assertRaises(BrokerError):self.service.admit_motion(body,changed,scene)
        changed=deepcopy(scene);changed['geometry']['epoch']+=1
        with self.assertRaises(BrokerError):self.service.admit_motion(body,row,changed)
        changed=deepcopy(scene);changed['produced_at']-=1
        with self.assertRaises(BrokerError):self.service.admit_motion(body,row,changed)
        self.service.job['state']='CANCELLED'

    def test_peer_motion_cannot_reuse_a_checked_stationary_disc(self):
        self.ready(plan());row=self.fleet.robots[self.robot];scene=self.fleet.navigation_scene
        peer=deepcopy(row);peer['pose']['position_m']=[2.5,2.5,0];peer['robot_id']='peer';self.fleet.robots['peer']=peer
        body=dict(request_id='checked-peer',payload=dict(text='forward .2 m'))
        with self.fleet.lock:
            self.service.motion_pin=dict(request_id='checked-peer',text='forward .2 m',pose=deepcopy(row['pose']['position_m']),binding=scene['binding'],geometry=deepcopy(scene['geometry']),peers=self.service._peer_context())
            self.service.admit_motion(body,row,scene)
            peer['pose']['position_m'][0]-=.01
            with self.assertRaises(BrokerError):self.service.admit_motion(body,row,scene)
            peer['_task']={'task_id':'another-existing-finite'}
            with self.assertRaisesRegex(BrokerError,'Stop every other'):
                self.service.admit_motion(body,row,scene)
        with self.assertRaisesRegex(BrokerError,'Stop every other'):
            self.service.run('owner',self.service.job['plan_sha256'])
        self.assertIsNone(row['_task']);self.fleet.robots.pop('peer')
    def test_current_saved_source_change_blocks_run_before_any_child(self):
        self.ready(plan());self.service.source_binding=lambda:'new-saved-state'
        with self.assertRaisesRegex(BrokerError,'Saved scene changed'):self.service.run('owner',self.service.job['plan_sha256'])
        self.assertIsNone(self.fleet.robots[self.robot]['_task'])
    def test_old_stop_receipt_cannot_delete_a_new_pending_stop(self):
        old=dict(request_id='old',motion_epoch='a');new=dict(request_id='new',motion_epoch='b')
        self.service._set_pending_stop(old);self.service._set_pending_stop(new)
        self.assertFalse(self.service._clear_pending_stop(old));self.assertIs(self.service.pending_stop,new)
        self.service.pending_stop=None
    def test_changed_scene_and_physical_contract_are_not_silent_fallbacks(self):
        self.ready(plan());self.fleet.robots[self.robot]['kind']='physical'
        row=self.fleet.robots[self.robot];self.service.job['proposal_binding'][1]='physical'
        try:
            with self.assertRaisesRegex(BrokerError,'Prepare'):
                self.service.run('owner',self.service.job['plan_sha256'])
            self.assertFalse(self.service.job['physical_authority']);self.assertIsNone(row['_task'])
        finally:self.fleet.robots[self.robot]['kind']='sim'
    def test_actual_scan_archive_and_movement_in_dynamic_survey_are_partial_not_whole_room_pass(self):
        p=plan();p['limits']['distance_m']=1.7
        self.ready(p);self.service.run('owner',canonical_sha256(p))
        self.wait(lambda:self.service.job['state'] in {'COMPLETED','PARTIAL','FAILED'},seconds=8)
        self.assertEqual(self.service.job['state'],'PARTIAL',self.service.job)
        self.assertGreater(self.service.job['segments'],1);self.assertGreater(self.service.job['measured_coverage']['observations'],1)
        self.assertLess(math.dist(self.fleet.robots[self.robot]['pose']['position_m'][:2],[1,1]),.05)
        self.assertFalse(self.service.job['whole_room_coverage_verified'])
        self.assertTrue((self.service.root/('a'*32)/'observed-grid.json').exists())


if __name__=='__main__':unittest.main()
