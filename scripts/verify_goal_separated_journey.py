# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit synthetic reference/qualification -> real separated App/Isaac/Chrome.

No production robot registration, SSH, devices, provider or deployment. The
existing native matcher/guards run in a local peer, never a frozen pose double.
Secrets exist only in memory/environment and are excluded from result files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))


def synthetic_output_count(rows):
    """ObservedLink records [linear, angular, elapsed], not session-event dicts.

    elapsed is the measured synthetic spin interval including scheduling, not
    the commanded segment duration. Native segment expiry is checked by the
    worker; do not relabel this observation as a <=50ms command receipt.
    """
    import math
    if type(rows) is not list:raise ValueError('SYNTHETIC_PUBLICATION_SHAPE')
    count=0
    for row in rows:
        if (type(row) is not list or len(row)!=3
                or any(type(value) not in (int,float) or not math.isfinite(value) for value in row)
                or abs(row[0])>.03 or abs(row[1])>.20 or row[2]<0):
            raise ValueError('SYNTHETIC_PUBLICATION_SHAPE_OR_LIMIT')
        count+=bool(row[0] or row[1])
    return count


def write(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')


def profile_query_receiver(controller,output):
    """Opt-in local diagnosis. Keep function metadata only, never frame locals.

    Profiled attempts are diagnostic, not performance acceptance: the sampler
    adds overhead. Neither this wrapper nor its timers change robot time/ages.
    """
    import cProfile
    import threading
    from collections import Counter
    original=controller._receive_localization
    count=[0]
    def receive(value,session):
        count[0]+=1;index=count[0];stop=threading.Event();stacks=Counter();samples=[0]
        def sample():
            while not stop.wait(.003) and samples[0]<256:
                for frame in sys._current_frames().values():
                    stack=[]
                    for _ in range(32):
                        if frame is None:break
                        stack.append((frame.f_code.co_filename,frame.f_code.co_name,frame.f_lineno));frame=frame.f_back
                    stacks[tuple(stack)]+=1
                samples[0]+=1
        thread=threading.Thread(target=sample,daemon=True,name='tp-test-query-sampler');thread.start()
        profile=cProfile.Profile();started=time.perf_counter();failure=None
        profile.enable()
        try:return original(value,session)
        except Exception as exc:failure=type(exc).__name__;raise
        finally:
            profile.disable();elapsed=time.perf_counter()-started;stop.set();thread.join(1.)
            entries=[]
            for row in profile.getstats():
                code=row.code
                if isinstance(code,str):name={'file':'<builtin>','function':code,'line':0}
                else:
                    path=Path(code.co_filename)
                    name={'file':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name,
                          'function':code.co_name,'line':code.co_firstlineno}
                entries.append({**name,'calls':row.callcount,'total_s':row.totaltime,'own_s':row.inlinetime})
            def location(p):
                path=Path(p)
                return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
            write(output/f'query-profile-{index}.json',{'diagnostic_only':True,'elapsed_s':elapsed,
                'failure_type':failure,'samples':samples[0],'sampler_exited':not thread.is_alive(),
                'functions':sorted(entries,key=lambda row:row['total_s'],reverse=True)[:80],
                'stacks':[{'count':hits,'frames':[{'file':location(p),'function':f,'line':n} for p,f,n in frames]}
                          for frames,hits in stacks.most_common(80)]})
    controller._receive_localization=receive


def backend(output,*,profile_queries=False,profile_goal_watch=False,task_loop=False,soak_seconds=0,ui_fault=None):
    from threading import RLock
    from types import SimpleNamespace
    from unittest.mock import patch
    from tests.integration.test_survey_reference import SurveyReferenceTests
    from tests.integration.test_automatic_demo_service import GEOMETRY
    from tests.integration.test_a2_room_recipe import NoGateway
    from scripts.rehearse_offline_app import NoCredentials
    from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore,LocalApiServer
    from twinpulse_app.automatic_demo_service import AutomaticDemoService
    from twinpulse_app.automatic_mission_service import AutomaticMissionService
    from twinpulse_app.physical_controller import PhysicalController
    from twinpulse_app.remote_observed_adapter import RemoteObservedFactory
    from twinpulse_app.chat_goal_navigation import ChatGoalNavigation
    from twinpulse_app.chat_inspection_visual import load_current_source
    from twinpulse_app.goal_demonstration import GoalDemonstration
    if profile_goal_watch:
        # Isolated diagnostic child only. Capture scoped watch stacks without
        # arguments/locals; profiled timing cannot count as acceptance.
        from twinpulse_app.remote_observed_adapter import RemoteObservedAdapter
        original_watch=RemoteObservedAdapter._goal_watches;watch_count=[0]
        def watch(adapter,stop,safety):
            watch_count[0]+=1;folder=output/f'goal-watch-profile-{watch_count[0]}'
            folder.mkdir()
            holder=SimpleNamespace(_receive_localization=lambda *_:original_watch(adapter,stop,safety))
            profile_query_receiver(holder,folder)
            return holder._receive_localization(None,None)
        RemoteObservedAdapter._goal_watches=watch
    state=output/'runtime';project='reference_room';capture=SurveyReferenceTests();capture.setUp();capture.root=state
    server=factory=controller=automatic=None;registration=None;storage_patch=None
    result={'status':'FAIL','robot_connections':0,'qualification':'EXPLICIT_TEST_ONLY_NOT_PHYSICAL_ACCEPTANCE'}
    peers=[]
    try:
        _,raycast=capture.capture();prior=capture.load()
        automatic=AutomaticDemoService(state,project,geometry_loader=lambda:GEOMETRY,
            room_loader=lambda root,pid:load_current_source(root,pid)['room'])
        automatic.room_scene_loader=lambda root,pid:load_current_source(root,pid)['scene']
        def command(*_):
            peer=output/f'synthetic-peer-{len(peers)}';peer.mkdir();peers.append(peer)
            fault=json.loads((output/'fault.json').read_text(encoding='utf-8')) if (output/'fault.json').exists() else {}
            world={'vertices':[a for a,_ in raycast.outline['segments']],
                'start':[-.1,-.6,.1],'unique_sessions':True,'profile_processing':True}
            if task_loop and len(peers)>1:
                previous=peers[-2]/'idle-report.json'
                if not previous.is_file():raise ValueError('CONTINUOUS_SYNTHETIC_WORLD_PREVIOUS_REPORT_REQUIRED')
                world['start']=json.loads(previous.read_text())['synthetic_final_pose']
                world['continued_from_peer']=peers[-2].name
            if fault.get('case')=='low_battery':world['voltage_v']=11.19
            if fault.get('case')=='stale':world['output_delay_s']=.21
            if fault.get('case')=='progress_stall':world['fault']='progress_stall'
            if ui_fault:
                world.update(fault='progress_stall' if ui_fault=='stall' else 'moving_stale_scan',combined_halt_fault=True)
            write(peer/'synthetic-world.json',world)
            return [sys.executable,'-B',str(ROOT/'tests/fixtures/idle_reference_robot_process.py'),str(peer)]
        controller=PhysicalController(state,command=command)
        if profile_queries:profile_query_receiver(controller,output)
        factory=RemoteObservedFactory(controller,state,project)
        factory.reference_loader=lambda key:capture.load(key)
        factory.room_revision_loader=lambda:automatic.photo_store.current(automatic.room_loader(state,project))['effective_revision']
        mission=AutomaticMissionService(automatic,adapter_factory=factory)
        if ui_fault:
            # Explicit isolated test injections, not real disk exhaustion or
            # altered production guards. Native estimator and input loop stay real.
            from twinpulse_app.remote_observed_adapter import RemoteObservedAdapter
            original_close=RemoteObservedAdapter.close
            def failed_close(adapter):
                original_close(adapter)
                if adapter.started:raise ValueError('OWNED_SENSOR_STOP_UNCONFIRMED')
            RemoteObservedAdapter.close=failed_close
            original_open=Path.open
            def full(path,*args,**kwargs):
                if path.is_relative_to(state) and 'automatic-mission' in path.parts and (args[0] if args else kwargs.get('mode','r'))=='x':
                    import errno
                    raise OSError(errno.ENOSPC,'TEST_ONLY_STORAGE_CANARY')
                return original_open(path,*args,**kwargs)
            storage_patch=patch.object(Path,'open',full);storage_patch.start()
        store=ProjectStore.for_project(state,project)
        app=ApplicationService(NoGateway(),project_store=store,project_id=project)
        broker=CommandBroker(project_id=project)
        workflow=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
        draft=app.site_draft
        workflow.resume_saved_scene(project,draft.site.scene.revision,draft.input_revision.digest)
        server=LocalApiServer(broker,product_bootstrap_secret=os.environ.pop('TWINPULSE_PRODUCT_BOOTSTRAP'),
            engine_bootstrap_secret=os.environ.pop('TWINPULSE_ENGINE_BOOTSTRAP'),bootstrap_ttl_s=300.,
            product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',
            session_history_root=state,credential_store=NoCredentials())
        server.automatic_mission.close();server.automatic_demo.close()
        server.automatic_demo=automatic;server.automatic_mission=mission
        # Keep the existing product inspection panel on the SAME mission
        # instance as navigation/API. A stale retired service reports idle
        # and repeats expensive model admission during the driving heartbeat.
        server.conversation.inspection.mission=mission
        assert server.conversation.inspection.mission is server.automatic_mission
        # The ONLY admission double. No persisted target profile/stop receipt
        # is created, no production registration or scene/matcher substituted.
        preparation=SimpleNamespace(snapshot=lambda owner:dict(owned=True,state='LINKED'),_independent_busy=lambda **_:None)
        nav=ChatGoalNavigation(mission,workflow,preparation,RLock(),SimpleNamespace(reference=lambda _:prior['map_id']))
        nav.demonstration=GoalDemonstration(broker,nav._scene,
            scene_guard_factory=lambda:mission._revision_guard(automatic.room_loader(state,project)))
        server.conversation.navigation=nav
        server.conversation._state.update(mode='REAL',robot_id='turtlebot3_burger')
        server.conversation._message('assistant','Offline integration rehearsal. Qualification and sensor inputs are synthetic; no physical robot is connected.')
        server.conversation._persist()
        registration=patch('twinpulse_app.remote_observed_adapter.ObservedReleaseRegistration',return_value=lambda _:{});registration.start()
        server.start();write(output/'backend-ready.json',{'base_url':server.base_url,'pid':os.getpid()})
        deadline=time.monotonic()+max(420.,soak_seconds+300.)
        while not (output/'backend-stop').exists() and time.monotonic()<deadline:time.sleep(.1)
        if time.monotonic()>=deadline:raise TimeoutError('OWNED_BACKEND_DEADLINE')
        result['original_survey_unchanged']=capture.path.read_bytes()==capture.original
        result['status']='PASS' if result['original_survey_unchanged'] else 'FAIL'
        result['operations']=[op.public() for op in broker._operations.values()]
        result['goal_job']=mission.snapshot(nav.owner)['job'] if nav.owner else None
    except Exception as exc:
        import traceback
        traceback.print_exc();result.update(error_type=type(exc).__name__,error=str(exc)[:1200])
    finally:
        for label,value,method in (('server',server,'stop'),('factory',factory,'close'),('controller',controller,'close'),
                ('automatic',automatic,'close'),('registration',registration,'stop'),('capture',capture,'doCleanups')):
            if value:
                try:getattr(value,method)()
                except Exception as exc:result.setdefault('cleanup_errors',[]).append({'component':label,'type':type(exc).__name__});result['status']='FAIL'
        if storage_patch:storage_patch.stop()
        result['peer_count']=len(peers)
        # Execution alone is insufficient: reopen every saved control session,
        # including the delayed negative case, and verify native cleanup/raw.
        try:
            from twinpulse_app.session_history import review_session
            sessions=state/'artifacts/manual-control'
            result['archives']=[{'job_id':folder.name,'mode':review_session(state,folder.name)['mode']}
                for folder in sessions.iterdir() if folder.is_dir()]
            result['peer_results']=[]
            for peer in peers:
                report=json.loads((peer/'idle-report.json').read_text(encoding='utf-8'))
                movement=synthetic_output_count(report['synthetic_published'])
                item={'peer':peer.name,'status':report['status'],'reason':report.get('reason'),
                    'nonzero_outputs':movement,'cleanup_confirmed':report.get('cleanup_confirmed') is True,
                    'synthetic_spin_elapsed_max_s':max((row[2] for row in report['synthetic_published']),default=None),
                    'sensor_cleanup_confirmed':report.get('sensor_cleanup_confirmed') is True}
                result['peer_results'].append(item)
                if not item['cleanup_confirmed'] or not item['sensor_cleanup_confirmed']:
                    raise ValueError('SYNTHETIC_PEER_CLEANUP_UNCONFIRMED')
                if (peer/'synthetic-world.json').exists() and json.loads((peer/'synthetic-world.json').read_text()).get('output_delay_s'):
                    if movement:raise ValueError('DELAYED_PEER_NONZERO_OUTPUT')
        except Exception as exc:
            result.update(status='FAIL',archive_error_type=type(exc).__name__,archive_error=str(exc)[:160])
        write(output/'backend-result.json',result)
    return 0 if result['status']=='PASS' else 1


def timing(output):
    """Pair same-domain sequence evidence, never subtract PC and robot clocks."""
    rows=[]
    for path in sorted((output/'runtime/artifacts/manual-control').glob('*/session.jsonl')):
        journal=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        generated={r['data']['sequence']:r for r in journal if r['kind']=='input_received' and r['data']['action']=='watch'}
        sent={r['data']['sequence']:r for r in journal if r['kind']=='pipe_written' and r['data']['action']=='watch'}
        accepted=[r['data']['event'] for r in journal if r['kind']=='robot_event' and r['data']['event']['kind']=='accepted'
            and r['data']['event']['data']['action']=='watch']
        def gaps(values):
            times=[r['t'] for r in values];return max([b-a for a,b in zip(times,times[1:])],default=0.)
        rows.append({'job_id':path.parent.name,'clock_domains':'PC_AND_ROBOT_REPORTED_SEPARATELY',
            'generation_count':len(generated),'write_count':len(sent),'robot_accept_count':len(accepted),
            'max_pc_generation_gap_s':gaps(list(generated.values())),
            'max_robot_accept_gap_s':gaps(accepted),
            'max_pc_generation_to_write_s':max([sent[k]['t']-r['t'] for k,r in generated.items() if k in sent],default=0.),
            'max_pipe_write_s':max([r['data']['pipe_write_s'] for r in sent.values()],default=0.),
            'localization':[r['data'] for r in journal if r['kind'] in {'localization_observation','localization_request_failed','localization_validation_rejected','localization_return_rejected','transport_error'}]})
    return rows


def soak_resource_summary(samples):
    """Report every counter before judging fixed, predeclared budgets."""
    active=[row for row in samples if row['soak_active']]
    if len(active)<110:raise ValueError('SOAK_RESOURCE_COVERAGE_REQUIRED')
    summary={};failures=[]
    for name,budget in (('backend',128*1024**2),('browser',256*1024**2),('engine',1024*1024**2)):
        values=[row['owned_children'][name]['private_bytes'] for row in active[4:]]
        growth=max(values)-min(values)
        summary[name]={'minimum_private_bytes':min(values),'maximum_private_bytes':max(values),
                       'range_bytes':growth,'range_budget_bytes':budget}
        if growth>budget:failures.append('SOAK_'+name.upper()+'_MEMORY_BUDGET')
    return {'samples':len(active),'summary':summary,
            'maximum_artifact_bytes':max(row['artifact_bytes'] for row in samples),
            'policy':'POST_WARMUP_PRIVATE_RANGE_V1','physical_validation':'NOT_RUN',
            'accepted':not failures,'rejection_codes':failures}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--backend-child',action='store_true')
    parser.add_argument('--profile-queries',action='store_true')
    parser.add_argument('--task-loop',action='store_true')
    parser.add_argument('--loop-legs',type=int,choices=(2,6),default=2)
    parser.add_argument('--soak-seconds',type=int,choices=(0,1800),default=0)
    parser.add_argument('--resource-observer',action='store_true',help='Owned CDP browser without network body capture')
    parser.add_argument('--progress-fault',action='store_true')
    parser.add_argument('--ui-fault',choices=('stall','scan'),help='Coupled native halt/adapter close/report storage UI fault; synthetic only')
    parser.add_argument('--profile-goal-watch',action='store_true');args=parser.parse_args();output=args.output.resolve()
    if args.soak_seconds and not args.task_loop:parser.error('Soak requires the actual repeat-task journey')
    if args.resource_observer and (not args.task_loop or args.progress_fault or args.profile_queries or args.profile_goal_watch):
        parser.error('Resource observer requires an unprofiled normal repeat-task journey')
    if args.soak_seconds and (args.progress_fault or args.profile_queries or args.profile_goal_watch):
        parser.error('Soak cannot include faults or timing-altering profiling')
    if args.ui_fault and (args.task_loop or args.progress_fault or args.soak_seconds or args.profile_queries or args.profile_goal_watch):
        parser.error('Coupled UI faults require an unprofiled standalone journey')
    if args.backend_child:return backend(output,profile_queries=args.profile_queries,profile_goal_watch=args.profile_goal_watch,task_loop=args.task_loop,soak_seconds=args.soak_seconds,ui_fault=args.ui_fault)
    output.mkdir(parents=True,exist_ok=False)
    if args.progress_fault:(output/'fault.json').write_text(json.dumps({'case':'progress_stall'}),encoding='utf-8')
    result={'status':'FAIL','robot_connections':0,'provider_calls':0,'physical_validation':'NOT_RUN',
        'isaac':'NOT_RUN','browser':'NOT_RUN','qualification':'EXPLICIT_TEST_DOUBLE','checks':[],
        'query_profiling_diagnostic_only':args.profile_queries,
        'watch_profiling_diagnostic_only':args.profile_goal_watch}
    sources=['scripts/verify_goal_separated_journey.py','apps/twinpulse-web/e2e/goal-native-isaac.mjs',
        'apps/twinpulse-web/e2e/goal-resource-observer.mjs','apps/twinpulse-web/e2e/owned-chrome-observer.mjs',
        'scripts/twinpulse_engine_host.py','scripts/owned_process_metrics.py',
        'apps/twinpulse-web/src/TwinViewport.tsx','apps/twinpulse-web/src/chat.css',
        'apps/twinpulse-web/src/api.ts','apps/twinpulse-web/src/mission-cleanup.ts',
        'packages/twinpulse_app/src/twinpulse_app/api.py',
        'packages/twinpulse_app/src/twinpulse_app/physical_controller.py','packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py',
        'packages/twinpulse_app/src/twinpulse_app/chat_goal_navigation.py','packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
        'packages/twinpulse_app/src/twinpulse_app/goal_progress.py','tests/integration/test_goal_progress.py',
        'packages/twinpulse_app/src/twinpulse_app/goal_demonstration.py','packages/twinpulse_app/src/twinpulse_app/command_broker.py',
        'packages/twinpulse_app/src/twinpulse_app/chat_inspection.py','packages/twinpulse_app/src/twinpulse_app/chat_inspection_visual.py',
        'packages/twinpulse_core/src/twinpulse_core/revisions.py',
        'packages/twinpulse_app/src/twinpulse_app/robot_geometry_evidence.py',
        'tests/integration/test_goal_latency.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py','packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
        'packages/twinpulse_core/src/twinpulse_core/current_goal_preview.py','packages/twinpulse_robot_safety/mission_runtime.py',
        'packages/twinpulse_core/src/twinpulse_core/mission_telemetry.py','packages/twinpulse_core/src/twinpulse_core/observed_progress.py',
        'packages/twinpulse_core/src/twinpulse_core/cleanup_diagnostics.py','packages/twinpulse_robot_safety/cleanup_notes.py',
        'packages/twinpulse_robot_safety/teleop_worker.py',
        'scripts/robot_source_identity.py','apps/twinpulse-web/src/CurrentGoalReview.tsx','apps/twinpulse-web/src/conversation-types.ts',
        'packages/twinpulse_robot_safety/observed_runtime.py','packages/twinpulse_robot_safety/teleop_ros.py',
        'tests/fixtures/idle_reference_robot_process.py','tests/fixtures/observed_robot_process.py',
        'tests/fixtures/manual_robot_process.py',
        'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py','extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'packages/twinpulse_app/src/twinpulse_app/session_history.py',
        'extensions/twinpulse.extension/twinpulse/extension/runtime.py']
    sources+=['packages/twinpulse_app/src/twinpulse_app/goal_task_loop.py','tests/integration/test_goal_task_loop.py',
              'tests/integration/test_goal_task_chat.py','apps/twinpulse-web/src/ChatWorkspace.tsx',
              'apps/twinpulse-web/src/CurrentGoalReview.tsx','apps/twinpulse-web/src/conversation-types.ts']
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources};result['source_sha256']=hashes
    built={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()}
    result['web_sha256']=built
    children=[];logs=[]
    secret=secrets.token_urlsafe(32);product=secrets.token_urlsafe(32)
    env={**os.environ,'TWINPULSE_ENGINE_BOOTSTRAP':secret,'TWINPULSE_PRODUCT_BOOTSTRAP':product,'PYTHONDONTWRITEBYTECODE':'1'}
    def start(command,name,environment):
        log=(output/(name+'.log')).open('wb');logs.append(log)
        child=subprocess.Popen(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0);children.append((name,child));return child
    try:
        if not Path('C:/isaacsim/python.bat').is_file():raise ValueError('EXISTING_ISAAC_REQUIRED')
        child=start([sys.executable,'-B',str(Path(__file__)) ,str(output),'--backend-child']+
            (['--soak-seconds',str(args.soak_seconds)] if args.soak_seconds else [])+
            (['--profile-queries'] if args.profile_queries else [])+
            (['--task-loop'] if args.task_loop else [])+
            (['--profile-goal-watch'] if args.profile_goal_watch else [])+
            (['--ui-fault',args.ui_fault] if args.ui_fault else []),'backend',env)
        deadline=time.monotonic()+80.
        while not (output/'backend-ready.json').exists():
            if child.poll() is not None or time.monotonic()>=deadline:raise RuntimeError('BACKEND_START_FAILED')
            time.sleep(.1)
        base=json.loads((output/'backend-ready.json').read_text(encoding='utf-8'))['base_url']
        engine_env={**env,'TWINPULSE_BRIDGE_URL':base,'TWINPULSE_PROJECT_ID':'reference_room',
            'TWINPULSE_STATE_DIR':str(output/'engine-state'),
            'TWINPULSE_PROJECT_STATE_ROOT':str(output/'runtime'),'TWINPULSE_SESSION_HISTORY_ROOT':str(output/'runtime')}
        engine_env.pop('TWINPULSE_PRODUCT_BOOTSTRAP',None)
        start(['C:/isaacsim/python.bat',str(ROOT/'scripts/twinpulse_engine_host.py'),
            '--stop-file',str(output/'engine-stop'),'--result-file',str(output/'engine-result.json'),
            '--viewport-capture',str(output/'engine-capture.png'),'--headless','--maximum-runtime-s',str(args.soak_seconds+300 if args.soak_seconds else 300 if args.loop_legs==2 else 600)],'engine',engine_env)
        result['isaac']='ACTUAL_SEPARATE_ENGINE_STARTED_NOT_ACCEPTED'
        node_env={**os.environ,'TWINPULSE_VIEW_URL':base,'TWINPULSE_VIEW_BOOTSTRAP':product,'TWINPULSE_VIEW_OUTPUT':str(output)}
        if args.task_loop:node_env['TWINPULSE_TASK_LOOP']='1'
        node_env['TWINPULSE_TASK_LOOP_LEGS']=str(args.loop_legs)
        node_env['TWINPULSE_SOAK_SECONDS']=str(args.soak_seconds)
        if args.progress_fault:node_env['TWINPULSE_PROGRESS_FAULT']='1'
        if args.ui_fault:node_env['TWINPULSE_UI_FAULT']=args.ui_fault
        node=shutil.which('node')
        if not node:raise ValueError('EXISTING_NODE_REQUIRED')
        browser_script='goal-resource-observer.mjs' if args.resource_observer else 'goal-native-isaac.mjs'
        result['browser_observer']='OWNED_CDP_NO_NETWORK_CAPTURE' if args.resource_observer else 'PLAYWRIGHT_NETWORK_CAPTURE'
        browser=start([node,str(ROOT/'apps/twinpulse-web/e2e'/browser_script)],'browser',node_env)
        result['browser']='ACTUAL_CHROME_STARTED_NOT_ACCEPTED'
        deadline=time.monotonic()+(args.soak_seconds+270. if args.soak_seconds else 270. if args.loop_legs==2 else 570.)
        sampled=-float('inf');samples=[]
        while browser.poll() is None and time.monotonic()<deadline:
            if args.soak_seconds and time.monotonic()-sampled>=15.:
                from scripts.owned_process_metrics import sample_tree
                sampled=time.monotonic()
                row={'pc_monotonic_s':sampled,'owned_children':{name:sample_tree(proc.pid)
                    for name,proc in children if proc.poll() is None}}
                row['soak_active']=(output/'soak-started').exists() and not (output/'soak-ended').exists()
                row['artifact_bytes']=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
                if row['artifact_bytes']>2*1024**3:raise ValueError('SOAK_ISOLATED_ARTIFACT_2GIB_BUDGET')
                samples.append(row)
                with (output/'owned-resources.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush()
            time.sleep(.2)
        if browser.poll() is None:raise TimeoutError('OWNED_BROWSER_DEADLINE')
        if not (output/'browser.json').exists():raise RuntimeError('BROWSER_EXIT_WITHOUT_RESULT_'+str(browser.returncode))
        result['browser_result']=json.loads((output/'browser.json').read_text(encoding='utf-8'))
        if browser.returncode or result['browser_result']['status']!='PASS':raise RuntimeError('BROWSER_JOURNEY_FAILED')
        if args.resource_observer:
            cleanup=json.loads((output/'observer-profile-cleanup.json').read_text(encoding='utf-8'))
            if cleanup!={'status':'PASS','profile_removed':True,'owned_normal_exit':True,
                         'background_updates_suppressed':True,'user_profile_touched':False}:
                raise ValueError('OWNED_OBSERVER_PROFILE_CLEANUP_REQUIRED')
            result['observer_profile_cleanup']=cleanup
        result.update(status='PASS',isaac='SEPARATE_ACTUAL_ENGINE_AND_AUTHENTICATED_BRIDGE',browser='ACTUAL_BUILT_CHROME_PASS',
            checks=result['browser_result']['checks'])
        if args.soak_seconds:
            soak=result['browser_result']['soak']
            if soak['elapsed_s']<1800 or soak['completed_legs']<6:raise ValueError('SOAK_WALL_TIME_OR_PROGRESS_REQUIRED')
            result['soak_resources']=soak_resource_summary(samples)
            if not result['soak_resources']['accepted']:
                raise ValueError(result['soak_resources']['rejection_codes'][0])
    except Exception as exc:result.update(status='FAIL',error_type=type(exc).__name__,error=str(exc)[:1200])
    finally:
        # Stop only processes created in this invocation, using their normal
        # owned file protocol first. No PID search or unrelated termination.
        (output/'engine-stop').touch();(output/'backend-stop').touch()
        for name,child in reversed(children):
            try:child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.terminate();child.wait(timeout=10);result.setdefault('forced_owned_cleanup',[]).append(name);result['status']='FAIL'
        for log in logs:log.close()
        for name in ('backend','engine'):
            path=output/(name+'-result.json')
            if path.exists():result[name+'_result']=json.loads(path.read_text(encoding='utf-8'))
        result['timing']=timing(output)
        result['sources_unchanged']=hashes=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
        result['web_unchanged']=built=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()}
        result['owned_children_exited']=all(c.poll() is not None for _,c in children)
        if (not result['sources_unchanged'] or not result['web_unchanged']
                or result.get('backend_result',{}).get('status')!='PASS'
                or result.get('engine_result',{}).get('status')!='PASS'):
            result['status']='FAIL'
        # Actual current native rendering is separate from successful PhysX
        # preview/capture. A marker must visibly activate and then disappear.
        observations=result.get('engine_result',{}).get('mission_visual_observations',[])
        result['active_visual_acceptance']={
            'current_visible':any(o['status']=='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED'
                and o['visibility']=='inherited' for o in observations),
            'ended_hidden':bool(observations and observations[-1]['status']=='LAST_OBSERVATION_NOT_CURRENT'
                and observations[-1]['visibility']=='invisible'),
            'renderer_error':result.get('engine_result',{}).get('mission_visual_error')}
        if not all(result['active_visual_acceptance'][k] for k in ('current_visible','ended_hidden')) or result['active_visual_acceptance']['renderer_error']:
            result['status']='FAIL';result.setdefault('error','ACTUAL_CURRENT_RENDER_OR_ENDED_HIDE_NOT_CONFIRMED')
        write(output/'verification.json',result)
    print(json.dumps({k:result.get(k) for k in ('status','isaac','browser','error')}),flush=True)
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
