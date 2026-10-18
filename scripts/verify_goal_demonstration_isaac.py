# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual existing Isaac/broker exact reviewed-route receipt, no robot transport."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--route-revalidation',action='store_true')
    parser.add_argument('--native-handoff',action='store_true',help='Synthetic reference/qualification only; actual chat service, Isaac and native subprocess')
    args=parser.parse_args()
    if args.native_handoff:args.route_revalidation=True
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    result={'status':'FAIL','isaac':'NOT_RUN','browser':'NOT_RUN','robot_connections':0,
        'sensor_source':'EXPLICIT_SYNTHETIC_CURRENT_EVIDENCE','physical_validation':'NOT_RUN','checks':[],'runs':[]}
    sources=['scripts/verify_goal_demonstration_isaac.py','packages/twinpulse_core/src/twinpulse_core/goal_simulation.py',
        'packages/twinpulse_core/src/twinpulse_core/current_goal_preview.py','packages/twinpulse_core/src/twinpulse_core/site_simulation.py',
        'packages/twinpulse_app/src/twinpulse_app/goal_demonstration.py','packages/twinpulse_app/src/twinpulse_app/command_broker.py',
        'extensions/twinpulse.extension/twinpulse/extension/runtime.py','extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'extensions/twinpulse.extension/twinpulse/extension/bedroom_preview.py']
    if args.native_handoff:
        sources+=['packages/twinpulse_app/src/twinpulse_app/chat_goal_navigation.py',
            'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
            'packages/twinpulse_app/src/twinpulse_app/physical_controller.py',
            'packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py',
            'packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py',
            'packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
            'packages/twinpulse_core/src/twinpulse_core/reference_transport.py',
            'packages/twinpulse_robot_safety/mission_runtime.py','packages/twinpulse_robot_safety/observed_runtime.py',
            'tests/fixtures/idle_reference_robot_process.py']
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    result['source_sha256']=hashes
    sim=runtime=service=capture=controller=factory=automatic=mission=registration_patch=None
    try:
        project='default'
        if args.native_handoff:
            from copy import deepcopy
            from threading import RLock
            from types import SimpleNamespace
            from unittest.mock import patch
            from tests.integration.test_survey_reference import SurveyReferenceTests
            from tests.integration.test_automatic_demo_service import GEOMETRY
            from twinpulse_app.chat_inspection_visual import load_current_source,checked_source,derived_scene
            from twinpulse_app.automatic_demo_service import AutomaticDemoService
            from twinpulse_app.automatic_mission_service import AutomaticMissionService
            from twinpulse_app.physical_controller import PhysicalController
            from twinpulse_app.remote_observed_adapter import RemoteObservedFactory
            from twinpulse_app.chat_goal_navigation import ChatGoalNavigation
            from twinpulse_core.room_localization import compose
            project='reference_room';state=output/'runtime'
            capture=SurveyReferenceTests();capture.setUp();capture.root=state
            report,raycast=capture.capture();prior=capture.load()
            automatic=AutomaticDemoService(state,project,geometry_loader=lambda:GEOMETRY,
                room_loader=lambda root,pid:load_current_source(root,pid)['room'])
            automatic.room_scene_loader=lambda root,pid:load_current_source(root,pid)['scene']
            native_python=Path('C:/Users/jaewo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
            if not native_python.is_file():raise ValueError('EXISTING_OFFLINE_NATIVE_INTERPRETER_REQUIRED')
            peer=None
            controller=PhysicalController(state,command=lambda *_:[str(native_python),'-B',
                str(ROOT/'tests/fixtures/idle_reference_robot_process.py'),str(peer)])
            factory=RemoteObservedFactory(controller,state,project)
            factory.reference_loader=lambda key:capture.load(key)
            factory.room_revision_loader=lambda:automatic.photo_store.current(automatic.room_loader(state,project))['effective_revision']
            mission=AutomaticMissionService(automatic,adapter_factory=factory)
            # Explicit test-only admission seam. No target profile or on-site
            # qualification is asserted or persisted by this harness.
            preparation=SimpleNamespace(snapshot=lambda _:dict(owned=True,state='LINKED'),_independent_busy=lambda **_:None)
            navigation=ChatGoalNavigation(mission,None,preparation,RLock(),
                inspection=SimpleNamespace(reference=lambda _:prior['map_id']))
            registration_patch=patch('twinpulse_app.remote_observed_adapter.ObservedReleaseRegistration',return_value=lambda _:{} )
            registration_patch.start()
            result['qualification']='EXPLICIT_TEST_DOUBLE_NOT_TARGET_ACCEPTANCE'
            result['sensor_source']='EXISTING_MATCHER_REACTIVE_SYNTHETIC_RAYCAST_NO_FROZEN_POSE'
        from isaacsim import SimulationApp
        sim=SimulationApp({'headless':True,'width':960,'height':720});result['isaac']='STARTED'
        import omni.usd
        from pxr import UsdGeom
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse_app.command_broker import CommandBroker
        from twinpulse_app.goal_demonstration import GoalDemonstration
        from twinpulse_core.current_goal_preview import goal_preview
        from tests.integration.test_scene_changes import room_source
        from tests.integration.test_current_goal_preview import evidence
        omni.usd.get_context().new_stage()
        for _ in range(8):sim.update()
        stage=omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage,'/ExternalKeep').GetPrim().SetCustomDataByKey('marker','unchanged')
        scene=room_source().site.scene if not args.native_handoff else navigation._scene()
        runtime=TwinPulseRuntime();engine=IsaacSimulationAdapter(runtime,project_id=project)
        broker=CommandBroker(project_id=project);broker.register_engine(engine.engine_session_id,engine.stage_epoch)
        lease=broker.acquire_lease('goal-owner')['control_lease_id'];engine.update_control_lease(lease,True)
        broker.record_snapshot(engine.snapshot());service=GoalDemonstration(broker,lambda:scene)
        if args.native_handoff:
            navigation.demonstration=service
            def heartbeat():
                broker.renew_lease('goal-owner',lease);broker.record_snapshot(engine.snapshot())
            park=factory.park_review;resume=factory.resume_review
            def park_and_refresh(*a):
                park(*a);heartbeat()
            def resume_and_refresh(*a):
                value=resume(*a);heartbeat();return value
            factory.park_review=park_and_refresh;factory.resume_review=resume_and_refresh
        for index,text in enumerate(('Go x=.30 y=-1.8','Go x=0 y=-1.35')):
            if args.native_handoff:
                peer=output/('synthetic-peer-'+str(index));peer.mkdir()
                (peer/'synthetic-world.json').write_text(json.dumps({'vertices':[a for a,_ in raycast.outline['segments']],
                    'start':[-.1,-.6,.1],'unique_sessions':True}),encoding='utf-8')
                current=factory.preview_current('goal-owner',reference_key=prior['map_id'])
                start=compose(current['evidence']['room_from_map'],current['evidence']['pose_map'])
                target=[start[0]+(.15 if index==0 else 0.),start[1]+(0. if index==0 else .15)]
                review=navigation.prepare('goal-owner',f'Go x={target[0]} y={target[1]}')['plan']
                assert factory.owns_review('goal-owner',prior['map_id'],review)
                assert not controller.snapshot('goal-owner')['busy'] and factory.idle_job is None
                assert not navigation.can_confirm()
            else:
                current=evidence();current['project_id']='default';context={k:current[k] for k in ('project_id','source_revision','epoch')}
                review=goal_preview(scene,text,current,context,1.,revalidate_route=args.route_revalidation)['plan']
                service.start('goal-owner',scene,review)
            deadline=time.monotonic()+180.;commands=[];positions=[];last_renew=0.
            while service.worker.is_alive() and time.monotonic()<deadline:
                if time.monotonic()-last_renew>.5:
                    broker.renew_lease('goal-owner',lease);last_renew=time.monotonic()
                command=broker.claim(engine.engine_session_id,engine.stage_epoch)
                if command:
                    commands.append(command.command_type);receipt=engine.execute(command);broker.record_receipt(receipt)
                    result.setdefault('command_receipts',[]).append(receipt.to_dict())
                sim.update();snapshot=engine.snapshot();broker.record_snapshot(snapshot)
                if snapshot.telemetry_available and snapshot.position_m is not None:positions.append(snapshot.position_m)
                time.sleep(.001)
            service.worker.join(.5);job=service.snapshot('goal-owner')
            if job['state']!='COMPLETED':raise RuntimeError(str(job))
            assert service.passed('goal-owner',review['plan_id']),job
            assert commands==['build_site_scene','run','pause'],commands
            assert runtime.site_plan['route']==review['route']
            assert runtime.site_plan['review']==review and runtime.site_plan['physical_authority'] is False
            assert len(positions)>20
            line=UsdGeom.BasisCurves(stage.GetPrimAtPath('/World/TwinPulse/Presentation/GoalRoutePreview'))
            assert line.GetPrim().GetCustomDataByKey('reviewId')==review['plan_id']
            assert len(line.GetPointsAttr().Get())==1+len(review['route'])
            assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='unchanged'
            result['runs'].append({'review':review,'job':job,'commands':commands,'pose_count':len(positions),
                'start_pose':positions[0],'terminal_pose':positions[-1],'physics_steps':runtime.physics_steps})
            if args.native_handoff:
                assert navigation.can_confirm()
                navigation.confirm('goal-owner',review['plan_id'],time.time()*1000+1500)
                deadline=time.monotonic()+50.;last_renew=0.
                while mission.worker.is_alive() and time.monotonic()<deadline:
                    mission.snapshot('goal-owner')
                    if time.monotonic()-last_renew>.5:heartbeat();last_renew=time.monotonic()
                    sim.update();broker.record_snapshot(engine.snapshot());time.sleep(.001)
                mission.worker.join(.5);assert not mission.worker.is_alive()
                job=mission.snapshot('goal-owner')['job']
                result['runs'][-1]['native_job']=job
                native=json.loads((peer/'idle-report.json').read_text())
                result['runs'][-1]['native_report']=native
                assert job['state']=='MISSION_ARRIVED',job
                assert job['approved_preview']==review and native['cleanup_confirmed'] and native['sensor_cleanup_confirmed']
                assert any(v or w for v,w in native['synthetic_published'])
                assert capture.path.read_bytes()==capture.original
                assert not controller.snapshot('goal-owner')['busy']
        receipt=service.snapshot('goal-owner')['receipt'];engine.refresh_stage_epoch()
        broker.register_engine(engine.engine_session_id,'replaced-test-stage')
        assert not service.passed('goal-owner',receipt['review_id'])
        result['checks']=['two_exact_sensor_bound_routes_actual_burger_physx_arrival_and_frozen_receipts',
            'build_run_ack_not_arrival_route_points_and_review_digest_unchanged',
            'external_prim_preserved_engine_stage_change_invalidates_receipt_no_robot_commands']
        if args.native_handoff:result['checks'].append('chat_goal_service_park_actual_isaac_receipt_single_confirm_fresh_native_arrival_cleanup')
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        result.update(status='PASS',isaac='ACTUAL_PHYSX_EXACT_ROUTE_RECEIPT_PASS',source_sha256=hashes)
        stage.GetRootLayer().Export(str(output/'goal-demonstration-stage.usda'))
    except Exception as exc:
        import traceback
        traceback.print_exc();result.update(error_type=type(exc).__name__,error=str(exc)[:1600])
    finally:
        for name,value,method in (('mission',mission,'close'),('factory',factory,'close'),
                ('controller',controller,'close'),('automatic',automatic,'close'),('registration',registration_patch,'stop'),
                ('capture',capture,'doCleanups'),('demonstration',service,'close'),('runtime',runtime,'shutdown')):
            if value:
                try:getattr(value,method)()
                except Exception as exc:
                    result.setdefault('cleanup_errors',[]).append({'component':name,'type':type(exc).__name__,'error':str(exc)[:200]})
                    result['status']='FAIL'
        result['sources_unchanged']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        if not result['sources_unchanged']:result['status']='FAIL'
        (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if sim:sim.close()
    print(json.dumps({k:result.get(k) for k in ('status','isaac','error')}),flush=True)
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
