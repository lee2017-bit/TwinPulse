# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No prior lap: actual App/shared mission loop, output-reactive observations.

Private truth is used only by the raycaster/evaluator. No success/transform
injection, no robot, no timing qualification or independent metric claim.
"""
import copy
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_core.adaptive_mission_contract import adaptive_scope,nominal_room
from twinpulse_core.revisions import canonical_sha256
from tests.integration.test_automatic_demo_service import GEOMETRY
from tests.integration.test_automatic_photo_service import recipe
from tests.integration.test_automatic_mission_service import RaycastAdapter


class ColdAdapter(RaycastAdapter):
    def spin(self,dt):
        # Time continues during the asynchronous fit. Slow virtual transport
        # yields CPU to the actual fit; it does not freeze the mission clock.
        super().spin(dt);time.sleep(dt*.15)


class ColdStartTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def execute(self,identity,scale,start,target,*,fault=None,stop_at=None,stop_when_fit=False,photo_policy='align_only',commit_failure=False,mode='SURVEY_THEN_NAVIGATE',current_chat=False):
        outline,_=recipe(self.root,identity,scale)
        automatic=AutomaticDemoService(self.root,identity,geometry_loader=lambda:GEOMETRY)
        if current_chat:
            from twinpulse_app.chat_inspection_visual import load_current_source
            automatic.room_loader=lambda root,pid:load_current_source(root,pid)['room']
            automatic.room_scene_loader=lambda root,pid:load_current_source(root,pid)['scene']
        self.addCleanup(automatic.close);adapters=[]
        if commit_failure:
            def rejected_append(*args,**kwargs):raise ValueError('PHOTO_LEDGER_HEAD_CHANGED')
            automatic.photo_store.append=rejected_append
        def factory(prior,room,effective,goal):
            adapter=ColdAdapter(prior,room,effective,goal,outline=outline,start=start,fault=fault)
            if stop_at or stop_when_fit:
                original=adapter.receive
                def receive():
                    if stop_at and adapter.t>=20+stop_at:adapter.stop_requested=lambda:'force_stop'
                    if stop_when_fit and service.job['state']=='ALIGNING_PHOTO':service.stop('owner',service.job['job_id'],True)
                    return original()
                adapter.receive=receive
            adapters.append(adapter);return adapter
        factory.supports_local_correction=True
        service=AutomaticMissionService(automatic,adapter_factory=factory);self.addCleanup(service.close)
        goal={'mode':mode,'xy':target,'room_revision':service.readiness(None)['room_revision'],'duration_s':45.}
        service.start('owner',None,goal,photo_policy);service.worker.join(70);self.assertFalse(service.worker.is_alive())
        job=service.snapshot('owner')['job']
        path=self.root/'artifacts/automatic-mission'/identity/f"{job['job_id']}.json"
        report=json.loads(path.read_text())
        evidence=os.environ.get('TWINPULSE_PREFLIGHT_EVIDENCE')
        if evidence:
            repository=Path(__file__).resolve().parents[2]
            target=Path(evidence).resolve()
            if not target.is_relative_to(repository/'artifacts/demo-preflight'):
                raise ValueError('PREFLIGHT_EVIDENCE_OUTSIDE_OWNED_ROOT')
            folder=target/job['job_id'];folder.mkdir(parents=True,exist_ok=False)
            (folder/'mission-report.json').write_bytes(path.read_bytes())
            with (folder/'synthetic-raw.json').open('x',encoding='utf-8') as stream:
                json.dump({'scope':'OUTPUT_REACTIVE_SYNTHETIC_NOT_ROBOT',
                    'observations':adapters[0].raw,'commands':adapters[0].sent},stream)
        return job,adapters[0],report

    def test_same_start_correct_walls_appends_and_rebinds_before_current_goal_plan(self):
        from twinpulse_app.automatic_photo_store import AutomaticPhotoStore,load_automatic_room
        for identity,scale,start,target in (('correct_one',1.,[0.,-.6,0.],[.15,-.6]),
                                          ('correct_two',1.2,[-.2,-.6,0.],[-.05,-.6])):
            with self.subTest(room=identity):
                job,adapter,report=self.execute(identity,scale,start,target,photo_policy='correct_walls')
                self.assertEqual(job['state'],'MISSION_ARRIVED',{k:job.get(k) for k in ('state','error','cold_start','photo_correction')})
                self.assertEqual(job['photo_policy']['schema'],'mission-photo-correction-policy-1.0')
                self.assertNotEqual(job['original_goal']['room_revision'],job['goal']['room_revision'])
                for key in ('mode','xy','duration_s'):self.assertEqual(job['original_goal'][key],job['goal'][key])
                room=load_automatic_room(self.root,identity);current=AutomaticPhotoStore(self.root,identity).current(room)
                self.assertEqual(len(current['events']),1);self.assertEqual(current['effective_revision'],job['goal']['room_revision'])
                self.assertEqual(job['objects_revision'],current['effective_revision'])
                self.assertEqual(job['visual']['room_revision'],current['effective_revision'])
                self.assertEqual(job['photo_correction']['goal_revalidation'],'NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED')
                self.assertEqual(job['photo_correction']['isaac_geometry_status'],'RECOMPOSITION_REQUIRED')
                self.assertEqual(current['events'][0]['job_id'],job['job_id'])
                self.assertTrue(current['events'][0]['goal_revalidation_required'])
                self.assertFalse(current['events'][0]['motion_authorized']);self.assertFalse(report['physical_demo_ready'])
                self.assertLess(math.dist(adapter.world[:2],target),.10);self.assertEqual(adapter.velocity,(0.,0.))
                self.assertEqual(report['original_goal'],job['original_goal'])
                self.assertEqual(report['photo_alignment']['geometry_status'],'BOUNDED_WALL_PROPOSAL_VALIDATED')
                self.assertEqual(report['photo_alignment']['goal_binding']['goal'],job['goal'])

    def test_commit_failure_retains_actual_fit_proposal_and_exact_cause_without_rebinding(self):
        from twinpulse_app.automatic_photo_store import AutomaticPhotoStore,load_automatic_room
        job,adapter,report=self.execute('correct_commit_failure',1.,[0.,-.6,0.],[.15,-.6],
            photo_policy='correct_walls',commit_failure=True)
        self.assertEqual(job['state'],'FAILED');self.assertEqual(adapter.velocity,(0.,0.))
        self.assertEqual(job['goal'],job['original_goal']);self.assertNotIn('photo_correction',report)
        self.assertFalse(AutomaticPhotoStore(self.root,'correct_commit_failure').current(
            load_automatic_room(self.root,'correct_commit_failure'))['events'])
        self.assertEqual(report['photo_alignment']['geometry_status'],'BOUNDED_WALL_PROPOSAL_VALIDATED')
        self.assertNotIn('goal_binding',report['photo_alignment'])
        self.assertEqual(report['cold_start']['reason'],'PHOTO_LEDGER_HEAD_CHANGED')
        self.assertEqual(report['cold_start']['error_stage'],'PHOTO_ALIGNMENT')
        self.assertEqual(report['cold_start']['error_type'],'ValueError')
        self.assertIsNone(report['visual']['pose_room']);self.assertFalse(report['physical_demo_ready'])

    def test_stop_during_correcting_fit_appends_nothing(self):
        from twinpulse_app.automatic_photo_store import AutomaticPhotoStore,load_automatic_room
        from unittest.mock import patch
        import threading
        release=threading.Event()
        def slow_fit(*args,**kwargs):
            release.wait(3);return {'status':'MODEL_MISMATCH','reason':'REJECTED_FAILURE_FIXTURE'}
        with patch('twinpulse_core.cold_start_mission.align_photo_map',slow_fit):
            try:
                job,adapter,report=self.execute('correct_stop',1.,[0.,-.6,0.],[.15,-.6],photo_policy='correct_walls',stop_when_fit=True)
                self.assertEqual(job['state'],'FORCE_STOPPED');self.assertEqual(adapter.velocity,(0.,0.))
                room=load_automatic_room(self.root,'correct_stop')
                self.assertFalse(AutomaticPhotoStore(self.root,'correct_stop').current(room)['events'])
                self.assertNotIn('photo_correction',report)
            finally:release.set()

    def test_two_rooms_cold_start_one_start_actual_fit_then_goal(self):
        for identity,scale,start,target in (('cold_one',1.,[0.,-.6,0.],[.15,-.6]),
                                          ('cold_two',1.2,[-.2,-.6,0.],[-.05,-.6])):
            with self.subTest(room=identity):
                job,adapter,report=self.execute(identity,scale,start,target)
                self.assertEqual(job['state'],'MISSION_ARRIVED',{k:job.get(k) for k in ('state','error','cold_start')})
                self.assertLess(math.dist(adapter.world[:2],target),.10)  # Fixed plan O2/O4 fixture bound, not physical accuracy.
                self.assertEqual(adapter.consumed,1);self.assertEqual(adapter.velocity,(0.,0.))
                rows=report['events'];summary=next(e['data'] for e in rows if e['kind']=='cold_start_diagnostics')
                self.assertEqual(summary['stage'],'NAVIGATE');self.assertEqual(summary['alignment_status'],'ALIGNMENT_CANDIDATE')
                views=[e['data'] for e in rows if e['kind']=='cold_start_view'];self.assertGreaterEqual(len(views),8)
                self.assertGreaterEqual(max(math.dist(a['pose'][:2],b['pose'][:2]) for a in views for b in views),.4)
                reasons={e['data']['decision']['reason'] for e in rows if e['kind']=='mission_decision'}
                self.assertTrue({'SURVEY_RETURN_FOR_HELD_OUT_VIEWS','PHOTO_FIT_WHEELS_IDLE','PHOTO_CANDIDATE_RECHECK_CURRENT_SENSOR'}<=reasons)
                self.assertIsNone(report['prior_map_revision']);self.assertEqual(report['physical_validation'],'NOT_RUN')
                self.assertFalse(report['motion_authorized']);self.assertTrue(report['visual']['pose_room'])

    def test_stop_during_survey_never_arrives_or_starts_photo_goal(self):
        job,adapter,report=self.execute('cold_stop',1.,[0.,-.6,0.],[.15,-.6],stop_at=2.)
        self.assertEqual(job['state'],'FORCE_STOPPED',job);self.assertEqual(adapter.velocity,(0.,0.))
        summary=next(e['data'] for e in report['events'] if e['kind']=='cold_start_diagnostics')
        self.assertEqual(summary['alignment_status'],'NOT_RUN');self.assertEqual(summary['stage'],'OUTBOUND')

    def test_stale_and_nan_source_stop_without_fitting(self):
        for fault in ('stale','scan','heartbeat'):
            with self.subTest(fault=fault):
                job,adapter,report=self.execute('cold_'+fault,1.,[0.,-.6,0.],[.15,-.6],fault=fault)
                self.assertEqual(job['state'],'FAILED',job);self.assertEqual(adapter.velocity,(0.,0.))
                self.assertTrue(job['error']);self.assertIsNone(report['visual']['pose_room'])

    def test_force_stop_while_fit_is_busy_rejects_late_answer(self):
        from unittest.mock import patch
        import threading
        entered=threading.Event();release=threading.Event();finished=threading.Event()
        def slow_rejected_fit(*args,**kwargs):
            entered.set();release.wait(5);finished.set()
            return {'status':'MODEL_MISMATCH','reason':'REJECTED_FAILURE_FIXTURE'}
        with patch('twinpulse_core.cold_start_mission.align_photo_map',slow_rejected_fit):
            try:
                job,adapter,report=self.execute('cold_fit_stop',1.,[0.,-.6,0.],[.15,-.6],stop_when_fit=True)
                self.assertTrue(entered.is_set());self.assertEqual(job['state'],'FORCE_STOPPED')
                self.assertEqual(adapter.velocity,(0.,0.));self.assertIsNone(report['visual']['pose_room'])
                before=len(adapter.sent);release.set();self.assertTrue(finished.wait(2))
                time.sleep(.03);self.assertEqual(len(adapter.sent),before)
                self.assertFalse(report['motion_authorized'])
            finally:release.set()

    def test_fit_failure_diagnostics_preserve_safe_cause_and_redact_arbitrary_text(self):
        from unittest.mock import patch
        import threading
        from twinpulse_core.cold_start_mission import ColdStartMission
        for cause,expected in (('PHOTO_SOURCE_REVISION_CHANGED','PHOTO_SOURCE_REVISION_CHANGED'),
                              ('credential=SECRET_CANARY source=C:/private','PHOTO_FIT_PROCESSING_FAILED')):
            with self.subTest(cause=expected):
                mission=ColdStartMission.__new__(ColdStartMission)
                mission.nominal={'objects':[],'height_m':.18};mission.cancelled=threading.Event()
                mission.failure=None;mission.failure_type=None;mission.alignment=None;mission.answer=None
                mission.stage='ALIGN';mission.views=[];mission.survey_map=None
                with patch('twinpulse_core.cold_start_mission.align_photo_map',side_effect=ValueError(cause)):
                    mission._fit({})
                diagnostic=mission.diagnostics()
                self.assertEqual(diagnostic['reason'],expected);self.assertEqual(diagnostic['error_stage'],'PHOTO_ALIGNMENT')
                self.assertEqual(diagnostic['error_type'],'ValueError');self.assertNotIn('SECRET_CANARY',str(diagnostic))

    def test_scope_v2_does_not_accept_browser_transform_or_invented_prior(self):
        _,objects=recipe(self.root,'scope',1.)
        goal={'mode':'SURVEY_THEN_NAVIGATE','xy':[0,0],'room_revision':'f'*64,'duration_s':45.}
        nominal=nominal_room(objects,.182,'f'*64)
        value={'schema':'observed-mission-scope-2.0','project_id':'scope','goal':goal,'reference':None,'alignment':None,'nominal':nominal}
        self.assertEqual(adaptive_scope(value),value)
        for change in ('v1','transform','prior','revision','nan','extra'):
            with self.subTest(change=change):
                bad=copy.deepcopy(value)
                if change=='v1':bad['schema']='observed-mission-scope-1.0'
                if change=='transform':bad['alignment']={'room_from_map':[0,0,0]}
                if change=='prior':bad['reference']={'revision':canonical_sha256({})}
                if change=='revision':bad['nominal']['room_revision']='e'*64
                if change=='nan':bad['nominal']['objects'][1]['shape']['dimensions_m'][0]=float('nan')
                if change=='extra':bad['nominal']['motion_authorized']=True
                with self.assertRaises(ValueError):adaptive_scope(bad)


if __name__=='__main__':unittest.main()
