"""No-device computation/late-result tests; not actual Isaac acceptance."""
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import time
import unittest
import ast
from pathlib import Path
from scripts.twinpulse_scan_worker import ScanWorker
from scripts.twinpulse_fleet_runtime import FleetRuntime
from twinpulse_core.lidar_geometry import SectionIndex


class ScanWorkerTests(unittest.TestCase):
    def wait(self,worker):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            result=worker.poll()
            if result is not None:return result
            time.sleep(.002)
        self.fail('bounded worker did not complete')

    def test_slow_scan_is_not_a_main_thread_wait_or_an_unbounded_queue(self):
        started=Event();release=Event()
        class Section:
            def scan(self,pose,*,cancel):
                started.set();release.wait(1);return [list(pose)]
        worker=ScanWorker()
        try:
            worker.submit(('original',),Section(),[1,2,3]);self.assertTrue(started.wait(1))
            began=time.monotonic()
            for _ in range(1000):
                self.assertFalse(worker.submit(('queued',),Section(),[4,5,6]));self.assertIsNone(worker.poll())
            self.assertLess(time.monotonic()-began,.2)
            release.set();result=self.wait(worker)
            self.assertEqual(result['token'],('original',));self.assertEqual(result['points'],[[1,2,3]])
        finally:release.set();self.assertFalse(worker.close()['worker_alive'])

    def test_original_geometry_result_and_error_no_partial_publication(self):
        section=SectionIndex([((-1,-1),(1,-1)),((1,-1),(1,1)),((1,1),(-1,1)),((-1,1),(-1,-1))])
        worker=ScanWorker()
        try:
            worker.submit(('t',),section,[0,0,.2]);result=self.wait(worker)
            self.assertEqual(result['points'],section.scan([0,0,.2]))
            bad=SimpleNamespace(scan=lambda *_,**__:(_ for _ in ()).throw(RuntimeError('failure')))
            worker.submit(('bad',),bad,[0,0,0]);result=self.wait(worker)
            self.assertEqual(result['error'],'RuntimeError');self.assertIsNone(result['points'])
        finally:self.assertFalse(worker.close()['worker_alive'])

    def test_close_cooperatively_reaps_active_scan(self):
        started=Event()
        class Section:
            def scan(self,_,*,cancel):
                started.set()
                while not cancel():time.sleep(.001)
                raise ValueError('LIDAR_SCAN_CANCELLED')
        worker=ScanWorker();worker.submit(('t',),Section(),[0,0,0]);self.assertTrue(started.wait(1))
        self.assertFalse(worker.close()['worker_alive']);self.assertIsNone(worker.poll())
        self.assertFalse(worker.submit(('t',),Section(),[0,0,0]))


class ResultBindingTests(unittest.TestCase):
    def test_cleanup_owners_are_independent_and_host_always_closes(self):
        runtime=FleetRuntime();closed=[]
        def fail():raise RuntimeError('ORIGINAL_REVOKE')
        runtime.scan_worker=SimpleNamespace(close=lambda:closed.append('scan') or dict(closed=True,worker_alive=False))
        runtime.planner=SimpleNamespace(shutdown=lambda **_:closed.append('planner'))
        runtime.bounds_notice=SimpleNamespace(Revoke=fail)
        result=runtime.close();self.assertEqual(closed,['scan','planner'])
        self.assertEqual(result['cleanup_errors'],[dict(owner='bounds_notice',error='RuntimeError')])
        # Compile the exact host helper without argparse or importing Isaac.
        import json
        tree=ast.parse((Path(__file__).resolve().parents[2]/'scripts/twinpulse_engine_host.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_finish_engine')
        ns=dict(json=json,print=lambda *_,**__:None,_write_json_atomic=lambda *_:fail())
        exec(compile(ast.Module(body=[node],type_ignores=[]),'engine-cleanup','exec'),ns)
        viewport=SimpleNamespace(stop=fail,diagnostic_snapshot=lambda:{},sent=0,dropped=0,capture_timeouts=0,capture_recoveries=0,last_error=None,transport_error=None)
        report=dict(error='ORIGINAL_FAILURE')
        ns['_finish_engine'](report,SimpleNamespace(close=lambda:closed.append('APP'),update=lambda:None),
            SimpleNamespace(snapshot=lambda:{},close=fail),viewport,None,None)
        self.assertEqual(closed[-1],'APP');self.assertEqual(report['error'],'ORIGINAL_FAILURE')
        self.assertIn(dict(owner='viewport_stop',error='RuntimeError'),report['cleanup_errors'])
        saved=[];ns['_write_json_atomic']=lambda _,v:saved.append(json.loads(json.dumps(v)))
        report=dict(status='PASS',error='ORIGINAL_FAILURE')
        ns['_finish_engine'](report,SimpleNamespace(close=fail,update=lambda:None),
            SimpleNamespace(snapshot=lambda:{},close=lambda:None),None,None,None)
        self.assertEqual(saved[0]['cleanup_status'],'PRE_CLOSE_COMPLETE')
        self.assertEqual(saved[0]['app_close']['state'],'PREPARED_FOR_ISAAC_CLOSE')
        self.assertEqual(saved[-1]['cleanup_status'],'PRE_CLOSE_FAILED');self.assertEqual(saved[-1]['error'],'ORIGINAL_FAILURE')
        self.assertIn(dict(owner='simulation_app',error='RuntimeError'),saved[-1]['cleanup_errors'])

    def test_actual_nonreturn_child_persists_handoff_before_os_exit(self):
        import subprocess,sys,tempfile,json
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'handoff.json'
            # Device-free subprocess executes the exact current helper then
            # os._exit, matching the SDK non-return boundary, not mocking return.
            code="""
import ast,json,os,sys
from pathlib import Path
from types import SimpleNamespace
tree=ast.parse(Path(sys.argv[1]).read_text())
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_finish_engine')
ns=dict(json=json,_write_json_atomic=lambda p,v:Path(p).write_text(json.dumps(v)))
exec(compile(ast.Module(body=[node],type_ignores=[]),'exact-host-helper','exec'),ns)
ns['_finish_engine'](dict(status='PASS'),SimpleNamespace(close=lambda:os._exit(0)),SimpleNamespace(snapshot=lambda:{},close=lambda:None),None,None,sys.argv[2])
raise AssertionError('unreachable after fast shutdown')
"""
            host=Path(__file__).resolve().parents[2]/'scripts/twinpulse_engine_host.py'
            run=subprocess.run([sys.executable,'-I','-c',code,str(host),str(target)],capture_output=True,text=True,timeout=5)
            self.assertEqual(run.returncode,0,run.stderr)
            value=json.loads(target.read_text())
            self.assertEqual(value['cleanup_status'],'PRE_CLOSE_COMPLETE')
            self.assertEqual(value['app_close']['state'],'PREPARED_FOR_ISAAC_CLOSE')
            self.assertTrue(value['app_close']['external_confirmation_required'])
            self.assertIn('TWINPULSE_ENGINE_HOST_RESULT=',run.stdout)

    def test_returning_close_last_stdout_failure_stays_in_saved_result(self):
        import json
        tree=ast.parse((Path(__file__).resolve().parents[2]/'scripts/twinpulse_engine_host.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_finish_engine')
        saved=[];printed=[]
        def output(*_,**__):
            printed.append(True)
            if len(printed)==2:raise BrokenPipeError('last result channel failed')
        ns=dict(json=json,print=output,_write_json_atomic=lambda _,v:saved.append(json.loads(json.dumps(v))))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'engine-cleanup','exec'),ns)
        result=dict(status='PASS',error='ORIGINAL_FAILURE')
        ns['_finish_engine'](result,SimpleNamespace(close=lambda:None),SimpleNamespace(snapshot=lambda:{},close=lambda:None),None,None,None)
        self.assertEqual(saved[-1]['cleanup_status'],'PRE_CLOSE_FAILED')
        self.assertEqual(saved[-1]['error'],'ORIGINAL_FAILURE')
        self.assertIn(dict(owner='close_return_stdout',error='BrokenPipeError'),saved[-1]['cleanup_errors'])

    def test_incomplete_or_failed_nested_join_is_not_preclose_complete(self):
        import json
        tree=ast.parse((Path(__file__).resolve().parents[2]/'scripts/twinpulse_engine_host.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_finish_engine')
        saved=[];ns=dict(json=json,print=lambda *_,**__:None,_write_json_atomic=lambda _,v:saved.append(json.loads(json.dumps(v))))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'engine-cleanup','exec'),ns)
        for bad in (dict(viewport_alive=True,fleet_alive=False,diagnostic_alive=False,scan_worker=dict(worker_alive=False)),
                    dict(viewport_alive=False,fleet_alive=False,diagnostic_alive=False,scan_worker=dict(worker_alive=False,cleanup_errors=[dict(error='Revoke')]))):
            viewport=SimpleNamespace(stop=lambda:None,diagnostic_snapshot=lambda:dict(join_status=bad),sent=0,dropped=0,
                capture_timeouts=0,capture_recoveries=0,last_error=None,transport_error=None)
            ns['_finish_engine']({},SimpleNamespace(close=lambda:None),SimpleNamespace(snapshot=lambda:{},close=lambda:None),viewport,None,None)
            self.assertEqual(saved[-1]['cleanup_status'],'PRE_CLOSE_FAILED')

    def fixture(self):
        runtime=FleetRuntime();runtime.identity=('e','s','revision');runtime.navigation_geometry_epoch=3
        robot=dict(epoch='connection',motion_epoch='motion',model_generation=2,scan_generation=4,scan=None)
        runtime.robots={'r':robot}
        request=dict(robot_id='r',connection_epoch='connection',motion_epoch='motion',lidar=True)
        token=runtime._scan_token('r',robot)
        sample=dict(robot_id='r',captured_at_ms=1000000.,position_m=[1,2,.3],height_m=.182,
            sensor_frame='original/USD/frame',geometry=dict(segments=344),diagnostic={})
        result=dict(token=token,points=[[.1,.2]],error=None,started_monotonic_s=1.,completed_monotonic_s=1.671,wall_s=.671,cpu_s=.01)
        runtime.scan_job=sample;runtime.scan_worker=SimpleNamespace(poll=lambda:result)
        return runtime,robot,request,result

    def test_old_pose_and_original_time_retained_not_completion_time(self):
        runtime,robot,request,result=self.fixture();robot['pose']=[8,9,2]
        with patch('scripts.twinpulse_fleet_runtime.time.time',return_value=1000.2):runtime._collect_scan([request])
        self.assertEqual(robot['scan']['captured_at_ms'],1000000.)
        self.assertEqual(robot['scan']['position_m'],[1,2,.3]);self.assertEqual(robot['scan_worst']['wall_s'],.671)

    def test_all_late_epoch_stop_off_and_expired_results_are_rejected(self):
        for case in ('scene','geometry','connection','motion','model','lidar_generation','off','visual','removed','expired'):
            with self.subTest(case=case):
                runtime,robot,request,result=self.fixture()
                if case=='scene':runtime.identity=('other','s','revision')
                if case=='geometry':runtime.navigation_geometry_epoch+=1
                if case=='connection':request['connection_epoch']='new'
                if case=='motion':request['motion_epoch']='stop'
                if case=='model':robot['model_generation']+=1
                if case=='lidar_generation':robot['scan_generation']+=1
                if case=='off':request['lidar']=False
                if case=='visual':request['visual_only']=True
                with patch('scripts.twinpulse_fleet_runtime.time.time',return_value=1000.4 if case=='expired' else 1000.2):
                    runtime._collect_scan([] if case=='removed' else [request])
                self.assertIsNone(robot['scan'])

    def test_two_robots_fair_without_rebuilding_identical_section(self):
        runtime=FleetRuntime();runtime.identity=('e','s','revision')
        runtime.robots={key:dict(epoch='c',motion_epoch='m',scan_at=0.) for key in ('a','b')}
        requests=[dict(robot_id=key,lidar=True) for key in ('a','b')]
        submitted=[]
        runtime.scan_worker=SimpleNamespace(busy=False,submit=lambda token,section,pose:submitted.append(token[2]) or True)
        geometry=dict(segments=344,triangles=3808,surfaces=['original'])
        with (patch('twinpulse_app.lidar_scene_geometry.sensor_pose',return_value=([0,0,0],.182,'model/scan')),
              patch('twinpulse_app.lidar_scene_geometry.scene_section',return_value=(object(),geometry)) as build):
            for now in (1.,1.2,1.4,1.6):runtime._schedule_scan(None,requests,now)
        self.assertEqual(submitted,['a','b','a','b']);self.assertEqual(build.call_count,1)
        # Exercise the actual backend diagnostic boundary, not just the producer.
        from twinpulse_core.fleet_diagnostics import checked_work,checked_fault
        prepare=runtime.robots['a']['scan_prepare']
        worker={**prepare,'started_monotonic_s':100.,'completed_monotonic_s':100.671,'wall_s':.671,'cpu_s':.016,
                'error':None,'captured_at_ms':100000.,'position_m':[1.,2.,3.]}
        work=dict(bounds_s=0.,model_authoring_s=0.,bounds_rebuilds=3,scan_s=0.,scan_error=None,
            scan_prepare_s=.001,scan_prepare=prepare,scan_worker=worker,scan_worker_worst=worker)
        self.assertEqual(checked_work(work),work)
        fault=dict(schema='fleet-first-fault-1.0',reason='ISAAC_UPDATE_STALLED',observed_monotonic_s=101.,
            observed_at_ms=101000.,elapsed_s=.7,current_work=work,previous_work=work,motion_epoch='m',task_id='t')
        self.assertEqual(checked_fault(fault),fault)
        for bad in ({**worker,'wall_s':float('nan')},{**worker,'unbounded':[]},{**worker,'position_m':[1,2]},
                    {**worker,'error':'x'*121},{**worker,'section_cache_hit':1},
                    {**worker,'wall_s':10**1000},{**worker,'position_m':[10**1000,0,0]}):
            self.assertIsNone(checked_work({**work,'scan_worker':bad}))
        for key in ('bounds_s','model_authoring_s','bounds_rebuilds','scan_prepare_s'):
            self.assertIsNone(checked_work({**work,key:10**1000}))
        self.assertIsNone(checked_work({**work,'host':dict(app_update_s=10**1000)}))
        for key in ('observed_monotonic_s','observed_at_ms','elapsed_s'):
            self.assertIsNone(checked_fault({**fault,key:10**1000}))
        for reason in ([],{},1):self.assertIsNone(checked_fault({**fault,'reason':reason}))

    def test_intermediate_off_on_invalidates_same_epoch_sample(self):
        runtime,robot,request,result=self.fixture();robot['scan_enabled']=True
        off={**request,'lidar':False};on={**request,'lidar':True}
        runtime.receive(dict(applied_revision='revision',robots=[off]))
        runtime.receive(dict(applied_revision='revision',robots=[on]))
        with patch('scripts.twinpulse_fleet_runtime.time.time',return_value=1000.2):runtime._collect_scan([on])
        self.assertIsNone(robot['scan'])


if __name__=='__main__':unittest.main()
