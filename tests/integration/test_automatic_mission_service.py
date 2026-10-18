# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""App -> actual mission loop -> output-reactive raycaster -> current matcher.

The simulated world is private to the transport fixture. The production matcher
receives odom/scan only, never evaluator truth or a prescribed success result.
No devices, paid provider or physical validation.
"""
from collections import deque
import copy
import json
import math
from pathlib import Path
import sys
import threading
from tempfile import TemporaryDirectory
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from twinpulse_app import CommandBroker,LocalApiServer
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.automatic_photo_store import load_automatic_room
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.local_navigation import LocalPose,LocalScan
from twinpulse_core.room_localization import compose,inverse
from tests.integration.test_automatic_photo_service import recipe,RaycastSource
from tests.integration.test_automatic_demo_service import GEOMETRY
from packages.twinpulse_core.tests.test_room_localization import scan_points


class RaycastAdapter:
    provenance='synthetic_raycast';frame_id='synthetic_room'
    def __init__(self,prior,room,effective,goal,*,outline,start,fault=None,gate=None):
        self.context={'project_id':room['project_id'],'source_revision':'e'*64,'epoch':1}
        self.tracker=CurrentMissionEvidence(prior['map'],prior['photo_alignment'],self.context,effective['effective_revision'],
            local_survey=goal['mode']!='NAVIGATE_TWIN_GOAL')
        self.outline=copy.deepcopy(outline);self.world=list(start);self.anchor=inverse(start)
        self.t=20.;self.velocity=(0.,0.);self.packets=deque();self.sequence=0;self.rows=[];self.reason='active'
        self.link=self;self.incoming=self;self.consumed=0;self.halted=0;self.sent=[];self.fault=fault;self.gate=gate
        self.stop_requested=lambda:None;self.request={'mission_id':'a'*32,'request_sha256':'b'*64,
            'waypoints':((.01,0.),),'duration_s':goal['duration_s'],'expires_s':70.,'binding':None}
        self.raw=[];self.last_scan=None
    def clock(self):return self.t
    def admit(self,goal):
        if self.fault=='admission':raise ValueError('MISSION_ADMISSION_CONTEXT_CHANGED')
    def safety(self):
        if self.fault=='battery' and len(self.sent)>4:raise ValueError('BATTERY_BUTTON_OR_SOURCE_AGE')
    def consume(self):
        self.consumed+=1
        if self.consumed!=1:raise ValueError('MISSION_ALREADY_CONSUMED')
    def receive(self):
        action=self.stop_requested()
        if action:
            self.sequence+=1;return {'sequence':self.sequence,'action':action,'challenge':'','age_ms':0}
        return self.packets.popleft() if self.packets else None
    def output(self,value):
        if self.fault=='heartbeat' and len(self.sent)>4:return
        self.sequence+=1;self.packets.append({'sequence':self.sequence,'action':'watch','challenge':value['challenge'],'age_ms':0})
    def navigation_snapshot(self):return {'fake_raw_count':len(self.raw),'physical_validation':'NOT_RUN'}
    def fresh(self):self.safety()
    def spin(self,dt):
        v,w=self.velocity;self.world[0]+=v*dt*math.cos(self.world[2]);self.world[1]+=v*dt*math.sin(self.world[2])
        self.world[2]+=w*dt;self.t+=dt
    def current(self,pose,now):return self.tracker.update(pose,self.last_scan,now)
    def observation_points(self):return scan_points(self.outline,self.world)
    def observed_decision(self,mission,result):pass
    def navigation_step(self,mission,binding,created,*,before_publish):
        before_publish()
        odom=compose(self.anchor,self.world)
        # Hidden world pose is used ONLY to generate fake observations.
        points=self.observation_points()
        ranges=tuple(math.hypot(*p) for p in points)
        if self.fault=='scan' and len(self.sent)>4:ranges=(float('nan'),)*120
        sample=self.t-.3 if self.fault=='stale' and len(self.sent)>4 else self.t
        pose=LocalPose(tuple(odom),sample,self.frame_id,'synthetic_model',self.provenance)
        self.last_scan=LocalScan(ranges,sample,'base_link','synthetic_model',self.provenance)
        self.raw.append({'odom':list(odom),'ranges':list(ranges),'t':self.t})
        result=mission.step(pose,self.last_scan,self.t,command_created_s=created)
        self.observed_decision(mission,result)
        if not result['allowed']:raise ValueError(result['reason'])
        before_publish();self.velocity=(result['linear_m_s'],result['angular_rad_s'])
        self.sent.append((self.t,*self.velocity))
        if self.gate and any(self.velocity):
            entered,release=self.gate;entered.set();release.wait(5)
        return {**result,'published_source_age_s':self.t-created}
    def navigation_stop_check(self,*_):self.safety()
    def halt(self):self.velocity=(0.,0.);self.halted+=1
    def close(self):self.halt()


class AutomaticMissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.outline,_=recipe(self.root,'mission_room',1.)
        self.automatic=AutomaticDemoService(self.root,'mission_room',source_factory=lambda *a:RaycastSource('mission_room',self.outline),geometry_loader=lambda:GEOMETRY)
        self.addCleanup(self.automatic.close)
        self.automatic.start('owner','a'*32,photo_policy='align_only');self.automatic.worker.join(15)
        job=self.automatic.snapshot('owner')['job'];self.assertEqual(job['state'],'COMPLETED',job)
        self.assertEqual(job['result']['photo_alignment']['status'],'ALIGNMENT_CANDIDATE')
        self.map_id=job['map_id'];self.adapters=[]
        self.service=AutomaticMissionService(self.automatic);self.addCleanup(self.service.close)
    def configure(self,start,fault=None,gate=None):
        def factory(prior,room,effective,goal):
            value=RaycastAdapter(prior,room,effective,goal,outline=self.outline,start=start,fault=fault,gate=gate)
            self.adapters.append(value);return value
        self.service.adapter_factory=factory
    def goal(self,xy):return {'mode':'NAVIGATE_TWIN_GOAL','xy':xy,'duration_s':45.,'room_revision':self.service.readiness(self.map_id)['room_revision']}
    def finish(self,owner='owner'):
        self.service.worker.join(30);self.assertFalse(self.service.worker.is_alive())
        return self.service.snapshot(owner)['job']
    def test_optional_stage_sink_exception_cannot_interrupt_arrival_halt_or_report(self):
        from unittest.mock import patch
        from twinpulse_core.execution_diagnostics import ExecutionStore,TraceContext
        store=ExecutionStore(self.root/'diagnostics','mission_room');self.addCleanup(store.flush)
        self.service.diagnostics=store;self.configure([0.,-.6,0.])
        original=TraceContext.child
        def reject_new_stage(context,stage,**values):
            if stage.startswith(('mission_adapter_','mission_phase_','mission_report_','mission_correction_')):
                raise OSError('PRIVATE_CREDENTIAL_CANARY')
            return original(context,stage,**values)
        with patch.object(TraceContext,'child',reject_new_stage):
            self.service.start('owner',self.map_id,self.goal([.05,-.6]));job=self.finish()
        self.assertEqual(job['state'],'MISSION_ARRIVED')
        self.assertEqual(job['report_status'],'SAVED');self.assertEqual(self.adapters[-1].velocity,(0.,0.))
        self.assertGreater(self.adapters[-1].halted,0);self.assertTrue(store.flush())
        detail=store.detail(store.list()['executions'][0]['execution_id'])
        self.assertEqual(detail['status'],'succeeded');self.assertNotIn('PRIVATE_CREDENTIAL_CANARY',json.dumps(detail))
        self.assertTrue(detail['health']['diagnostics_degraded'])
        self.assertGreaterEqual(detail['health']['storage_errors'],3)

    def test_two_starts_sensor_feedback_goal_not_old_pose_and_immutable_report(self):
        for start,target in (([0.,-.6,0.],[.15,-.6]),([-.3,-.4,.25],[-.14,-.4])):
            self.configure(start);self.service.start('owner',self.map_id,self.goal(target));job=self.finish()
            self.assertEqual(job['state'],'MISSION_ARRIVED',job)
            a=self.adapters[-1];self.assertLess(math.dist(a.world[:2],target),.10)
            self.assertEqual(a.consumed,1);self.assertGreater(a.halted,0);self.assertEqual(a.velocity,(0.,0.))
            self.assertGreater(len(a.sent),10);self.assertGreater(len(a.raw),10)
            self.assertFalse(job['motion_authorized']);self.assertTrue(job['report_revision'])
            path=self.root/'artifacts/automatic-mission/mission_room'/f"{job['job_id']}.json"
            report=json.loads(path.read_text());self.assertEqual(report['physical_validation'],'NOT_RUN')
            self.assertEqual({e['data']['action'] for e in report['events'] if e['kind']=='accepted'},{'watch'})
    def test_cleanup_failure_is_visible_saved_and_does_not_replace_first_failure(self):
        from twinpulse_core.execution_diagnostics import ExecutionStore
        store=ExecutionStore(self.root/'diagnostics','mission_room');self.addCleanup(store.flush);self.service.diagnostics=store
        for fault in (None,'battery'):
            with self.subTest(primary=fault):
                self.configure([0.,-.6,0.],fault=fault);original=self.service.adapter_factory
                def factory(*args):
                    value=original(*args)
                    def close():
                        value.halt();raise ValueError('OWNED_SENSOR_STOP_UNCONFIRMED')
                    value.close=close;return value
                self.service.adapter_factory=factory
                self.service.start('owner',self.map_id,self.goal([.05,-.6]));job=self.finish()
                self.assertEqual(job['state'],'FAILED');self.assertEqual(job['cleanup_error'],'OWNED_SENSOR_STOP_UNCONFIRMED')
                self.assertEqual(job['cleanup_error_type'],'ValueError');self.assertEqual(job['cleanup_stage'],'ADAPTER_CLEANUP')
                self.assertEqual(job['error'],'BATTERY_BUTTON_OR_SOURCE_AGE' if fault else 'OWNED_SENSOR_STOP_UNCONFIRMED')
                self.assertEqual(job['error_stage'],'RUN_CURRENT_MISSION' if fault else 'ADAPTER_CLEANUP')
                report=json.loads((self.root/'artifacts/automatic-mission/mission_room'/f"{job['job_id']}.json").read_text())
                self.assertEqual(report['cleanup_error'],job['cleanup_error']);self.assertEqual(report['error'],job['error'])
                self.assertEqual(report['visual']['state'],'FAILED');self.assertIsNone(report['visual']['pose_room'])
                self.assertEqual(report['visual']['scan_room'],[]);self.assertEqual(report['visual']['route_room'],[])
                self.assertEqual(report['visual']['revision'],__import__('twinpulse_core.revisions',fromlist=['canonical_sha256']).canonical_sha256(
                    {k:v for k,v in report['visual'].items() if k!='revision'}))
                self.assertEqual(self.adapters[-1].velocity,(0.,0.));self.assertFalse(report['physical_demo_ready'])
                self.assertTrue(store.flush())
                identity=store.list(query=job['job_id'])['executions'][0]['execution_id']
                detail=store.detail(identity)
                cleanup=next(s for s in detail['spans'] if s['stage']=='mission_adapter_cleanup')
                self.assertEqual(cleanup['status'],'failed');self.assertEqual(cleanup['metadata']['role'],'cleanup')
                self.assertEqual(detail['first_error']['error_code'],job['error'])
                self.assertEqual(next(s for s in detail['spans'] if s['stage']=='mission_report_save')['status'],'succeeded')
    def test_visual_contract_rejects_tamper_authority_room_and_nonfinite_goal(self):
        from twinpulse_app.automatic_mission_visual import checked_mission_visual
        from twinpulse_core.revisions import canonical_sha256
        identity='d'*32;goal=self.goal([.1,-.6]);room=load_automatic_room(self.root,'mission_room')
        visual={'session_id':identity,'pose_room':[0.,0.,0.],'goal_room':goal['xy'],
                'scan_room':[],'route_room':[],'trajectory_room':[],
                'motion_authorized':False,'physical_demo_ready':False}
        report={'project_id':'mission_room','job_id':identity,'goal':goal,'room_base_revision':room['revision'],
                'motion_authorized':False,'physical_demo_ready':False,'visual':visual}
        path=self.root/'artifacts/automatic-mission/mission_room'/f'{identity}.json';path.parent.mkdir(parents=True)
        for cause in ('tamper','authority','room','project','goal'):
            with self.subTest(cause=cause):
                value=copy.deepcopy(report)
                if cause=='authority':value['motion_authorized']=True
                if cause=='room':value['goal']['room_revision']='f'*64
                if cause=='project':value['project_id']='another_room'
                if cause=='goal':value['visual']['goal_room']=[50.,0.]
                value['visual']['revision']=canonical_sha256(value['visual'])
                revision=canonical_sha256(value);value['revision']=revision
                if cause=='tamper':value['job_id']='e'*32
                path.write_text(json.dumps(value),encoding='utf-8')
                with self.assertRaises(ValueError):checked_mission_visual(self.root,'mission_room',
                    {'kind':'automatic_mission_visual_v1','mission_id':identity,'manifest_sha256':revision})

    def test_failures_final_halt_no_fake_arrival(self):
        for fault in ('admission','heartbeat','stale','scan','battery'):
            self.configure([0.,-.6,0.],fault);self.service.start('owner',self.map_id,self.goal([.3,-.6]));job=self.finish()
            self.assertEqual(job['state'],'FAILED',job);self.assertTrue(job['error']);self.assertTrue(job['report_revision'])
            self.assertEqual(self.adapters[-1].velocity,(0.,0.));self.assertGreater(self.adapters[-1].halted,0)
    def test_local_survey_without_photo_pose_and_finish_stop(self):
        self.configure([-.3,-.4,.4]);goal={**self.goal([.08,0.]),'mode':'SURVEY_LOCAL'}
        self.service.start('owner',self.map_id,goal);job=self.finish()
        self.assertEqual(job['state'],'MISSION_ARRIVED',job)
        self.assertIsNone(job['visual']['pose_room']);self.assertFalse(job['motion_authorized'])
        gate=(threading.Event(),threading.Event());self.configure([0.,-.6,0.],gate=gate)
        started=self.service.start('owner',self.map_id,self.goal([.3,-.6]))['job'];self.assertTrue(gate[0].wait(10))
        self.service.stop('owner',started['job_id']);gate[1].set();job=self.finish()
        self.assertEqual(job['state'],'COMMAND_SEGMENT_STOPPED',job)
    def test_default_locked_order_ownership_stop_and_force_upgrade(self):
        with self.assertRaisesRegex(BrokerError,'No qualified current'):self.service.start('owner',self.map_id,self.goal([.2,-.6]))
        gate=(threading.Event(),threading.Event());self.configure([0.,-.6,0.],gate=gate)
        started=self.service.start('owner',self.map_id,self.goal([.3,-.6]))['job'];self.assertTrue(gate[0].wait(10))
        with self.assertRaises(BrokerError):self.service.stop('other',started['job_id'])
        with self.assertRaises(BrokerError):self.automatic.start('owner','b'*32)
        self.service.stop('owner',started['job_id']);self.service.stop('owner',started['job_id'],True)
        gate[1].set();job=self.finish();self.assertEqual(job['state'],'FORCE_STOPPED',job)
        self.assertEqual(self.adapters[-1].velocity,(0.,0.))
    def test_authenticated_api_exact_goal_shape_and_causal_worker(self):
        self.configure([0.,-.6,0.]);server=LocalApiServer(CommandBroker(project_id='mission_room'),product_bootstrap_secret='p'*43,engine_bootstrap_secret='e'*43)
        server.automatic_mission.close();server.automatic_demo.close();server.automatic_demo=self.automatic;server.automatic_mission=self.service
        server.start();self.addCleanup(server.stop)
        def req(path,body=None,headers=None):
            request=Request(server.base_url+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'Origin':server.base_url,'Content-Type':'application/json',**(headers or {})})
            with urlopen(request,timeout=10) as response:return json.loads(response.read()),dict(response.headers)
        state,headers=req('/v1/bootstrap',{'role':'product','secret':'p'*43})
        cookie=headers['Set-Cookie'].split(';')[0];auth={'Cookie':cookie,'X-TwinPulse-CSRF':state['csrf_token']}
        with self.assertRaises(HTTPError):req('/v1/product/automatic-demo/mission-start',{'map_id':self.map_id,'goal':{**self.goal([.15,-.6]),'authorized':True}},auth)
        started,_=req('/v1/product/automatic-demo/mission-start',{'map_id':self.map_id,'goal':self.goal([.15,-.6])},auth)
        self.service.worker.join(30);self.assertFalse(self.service.worker.is_alive())
        value,_=req('/v1/product/automatic-demo/mission',headers=auth)
        self.assertEqual(value['job']['state'],'MISSION_ARRIVED',value)
        self.assertEqual(value['job']['job_id'],started['job']['job_id'])


class MissionDiagnosticBoundaryTests(unittest.TestCase):
    def setUp(self):
        from twinpulse_core.execution_diagnostics import ExecutionStore
        from twinpulse_app.automatic_mission_service import _MissionDiagnostic
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=ExecutionStore(Path(self.temp.name)/'diagnostics','bounded');self.addCleanup(self.store.flush)
        self.trace=self.store.begin('observed_mission');self.diagnostic=_MissionDiagnostic(self.trace)

    def detail(self,status='succeeded'):
        self.trace.finish(status);self.assertTrue(self.store.flush());return self.store.detail(self.trace.execution_id)

    def test_mission_revision_metadata_accepts_only_sha256_not_free_text_or_numbers(self):
        from twinpulse_core.execution_diagnostics import metadata
        self.assertEqual(metadata({'map_revision':'a'*64,'alignment_revision':'SAFE_LOOKING_PRIVATE_CANARY',
            'correction_revision':7,'goal_room_revision':True}),{'map_revision':'a'*64})

    def test_unreceived_ack_is_unknown_even_if_outer_worker_succeeded_and_late_ack_is_ignored(self):
        self.diagnostic.wait_ack(correction_revision='a'*64)
        self.diagnostic.close('succeeded');self.diagnostic.accepted_ack(goal_room_revision='b'*64)
        ack=next(s for s in self.detail()['spans'] if s['stage']=='mission_correction_ack')
        self.assertEqual(ack['status'],'unknown');self.assertEqual(ack['metadata']['remote_outcome'],'unknown')
        self.assertNotIn('goal_room_revision',ack['metadata'])

    def test_skipped_phase_is_unknown_and_repeated_states_have_bounded_metadata(self):
        for index in range(1000):
            self.diagnostic.phase_observed({'stage':'OUTBOUND','map_revision':f'{index:064x}',
                'robot_t':index,'scan_room':[[1,2]],'reason':'PRIVATE CANARY'})
        self.diagnostic.phase_observed({'stage':'NAVIGATE'})
        self.diagnostic.close('cancelled')
        detail=self.detail('cancelled');spans={s['stage']:s for s in detail['spans']}
        self.assertEqual(spans['mission_phase_outbound']['status'],'unknown')
        self.assertEqual(spans['mission_phase_navigate']['status'],'cancelled')
        self.assertLessEqual(detail['event_count'],25)
        text=json.dumps(detail);self.assertNotIn('robot_t',text);self.assertNotIn('PRIVATE CANARY',text)


if __name__=='__main__':unittest.main()
