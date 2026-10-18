# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from unittest.mock import patch

from twinpulse_app import CommandBroker,LocalApiServer
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.bedroom_review import load_bedroom_source
from twinpulse_app.room_localization_review import RoomLocalizationReview,checked_localization_visual
from twinpulse_core.room_localization import PoseTimeline,scene_outline


def source():return load_bedroom_source()


def evidence(root,project,job):
    from packages.twinpulse_core.tests.test_room_localization import pose,scan_points
    outline=scene_outline(source()[0].site.scene.to_dict()['objects'])
    start=[0,-.5,.35];points=scan_points(outline,start)
    # A ray-cast with no synthetic TF authentication. This fake dataset tests
    # wiring only; real originals are verified in the separate stored run.
    ranges=[math.hypot(*p) for p in points]
    rows=[pose(1_000_000_000),pose(1_100_000_000)]
    return {'job_id':job,'source_revision':'a'*64,'boot_id':'fake-boot','release_id':'b'*64,
        'scans':[{'stamp_ns':1_050_000_000,'time_increment':0.,'angle_min':0.,
                  'angle_increment':math.tau/120,'ranges_m':ranges,'frame_id':'base_scan','raw_sequence':4}],
        'odom':rows,'timeline':PoseTimeline(rows),'diagnostics':{'decoded_counts':{'scan':1},'tf_static_count':0}}


import math


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.review=RoomLocalizationReview(self.root,'default',evidence_loader=evidence)
        self.revision=source()[1]['manifest_sha256']

    def test_product_record_saved_and_reposition_invalidates(self):
        report=self.review.analyse(self.revision,'a'*32,0)
        self.assertFalse(report['motion_authorized']);self.assertEqual(report['timing']['paired_frames'],1)
        self.assertEqual(len(list((self.root/'artifacts/room-localization-review').glob('*.json'))),1)
        self.review.invalidate();self.assertIsNone(self.review.snapshot()['result'])
        with self.assertRaises(BrokerError):self.review.goal(self.revision,report['revision'],report['epoch'],[0,0])

    def test_observation_map_does_not_load_photo_or_create_position_binding(self):
        self.review.source_loader=lambda: (_ for _ in ()).throw(AssertionError('Photo geometry must not be used'))
        report=self.review.observation_map('a'*32)
        self.assertFalse(report['photo_geometry_used']);self.assertFalse(report['physical_demo_ready'])
        self.assertFalse(report['timing']['acquisition_timing_verified'])
        self.assertEqual(report['paired_frames'],1);self.assertIsNone(self.review.localization.binding)
        path=self.root/'artifacts/session-observation-map'/(report['report_id']+'.json')
        from twinpulse_core.revisions import canonical_sha256
        body=json.loads(path.read_text());revision=body.pop('revision')
        self.assertEqual(canonical_sha256(body),revision)
        self.review.invalidate();self.assertIsNone(self.review.observation)

    def test_observation_invalidation_during_computation_is_explicit(self):
        def interrupted(root,project,job):
            self.review.invalidate();return evidence(root,project,job)
        self.review.evidence_loader=interrupted
        with self.assertRaisesRegex(BrokerError,'INVALIDATED_DURING'):self.review.observation_map('a'*32)
        self.assertIsNone(self.review.observation)

    def test_observation_build_revokes_previous_photo_position(self):
        candidate={'status':'GEOMETRIC_CANDIDATE','pose':[.2,.3,.4]}
        with patch('twinpulse_app.room_localization_review.RoomMatcher.match',return_value=candidate):
            previous=self.review.analyse(self.revision,'a'*32,0)
        self.assertIsNotNone(self.review.localization.binding)
        self.review.observation_map('b'*32)
        self.assertIsNone(self.review.localization.binding);self.assertIsNone(self.review.last)
        with self.assertRaises(BrokerError):self.review.goal(self.revision,previous['revision'],previous['epoch'],[0,0])

    def test_observation_empty_data_does_not_leave_previous_map(self):
        self.review.observation_map('a'*32)
        def empty(root,project,job):
            value=evidence(root,project,job);value['scans'][0]['ranges_m']=[None]*120;return value
        self.review.evidence_loader=empty
        with self.assertRaisesRegex(BrokerError,'NO_PAIRED_RETURNS'):self.review.observation_map('a'*32)
        self.assertIsNone(self.review.observation)

    def test_model_comparison_bound_to_observation_and_originals_without_goal(self):
        observed=self.review.observation_map('a'*32)
        report=self.review.compare_model(self.revision,'a'*32,observed['revision'])
        self.assertEqual(report['observation_revision'],observed['revision'])
        self.assertEqual(report['source_revision'],observed['source_revision'])
        self.assertFalse(report['geometry_changed']);self.assertFalse(report['motion_authorized'])
        self.assertIsNone(self.review.localization.binding);self.assertIsNone(self.review.last)
        self.assertEqual(len(list((self.root/'artifacts/observation-model-comparison').glob('*.json'))),1)
        with self.assertRaisesRegex(BrokerError,'CURRENT_OBSERVATION_REQUIRED'):
            self.review.compare_model(self.revision,'b'*32,observed['revision'])
        self.review.invalidate()
        with self.assertRaisesRegex(BrokerError,'CURRENT_OBSERVATION_REQUIRED'):
            self.review.compare_model(self.revision,'a'*32,observed['revision'])

    def test_sensor_map_saves_hashed_project_sources_without_photo_or_goal_binding(self):
        observed=self.review.observation_map('a'*32)
        self.review.source_loader=lambda: (_ for _ in ()).throw(AssertionError('Photo is not a sensor map'))
        self.review.localization.binding={'old':'photo binding'}
        body={'status':'SENSOR_MAP_GEOMETRIC_CANDIDATE','photo_geometry_used':False,
              'motion_authorized':False,'physical_demo_ready':False,'room_transform_created':False}
        with patch('twinpulse_app.room_localization_review.locate_in_sensor_map',return_value=body) as locate:
            report=self.review.locate_sensor_map('a'*32,observed['revision'],'b'*32,1)
        self.assertEqual(locate.call_args.args[2],1)
        self.assertEqual(report['project_id'],'default');self.assertEqual(report['query_job_id'],'b'*32)
        self.assertEqual(report['reference_source_revision'],'a'*64)
        self.assertEqual(report['query_source_revision'],'a'*64)
        self.assertFalse(report['room_transform_created']);self.assertIsNone(self.review.localization.binding)
        self.assertIsNone(self.review.snapshot()['result'])
        path=self.root/'artifacts/sensor-map-localization'/(report['report_id']+'.json')
        from twinpulse_core.revisions import canonical_sha256
        saved=json.loads(path.read_text());revision=saved.pop('revision')
        self.assertEqual(canonical_sha256(saved),revision)
        self.review.invalidate();self.assertIsNone(self.review.sensor_match)

    def test_sensor_map_current_reference_epoch_and_busy_preconditions(self):
        with self.assertRaisesRegex(BrokerError,'CURRENT_OBSERVATION_REQUIRED'):
            self.review.locate_sensor_map('a'*32,'none','b'*32,1)
        observed=self.review.observation_map('a'*32)
        for job,revision in (('b'*32,observed['revision']),('a'*32,'old')):
            with self.subTest(job=job),self.assertRaisesRegex(BrokerError,'CURRENT_OBSERVATION_REQUIRED'):
                self.review.locate_sensor_map(job,revision,'b'*32,1)
        # Starting a new photo review changes epoch without deleting the cached map.
        self.review.analyse(self.revision,'a'*32,0)
        for operation in (lambda:self.review.locate_sensor_map('a'*32,observed['revision'],'b'*32,1),
                          lambda:self.review.compare_model(self.revision,'a'*32,observed['revision'])):
            with self.assertRaisesRegex(BrokerError,'CURRENT_OBSERVATION_REQUIRED'):operation()
        self.review.work.acquire()
        try:
            with self.assertRaisesRegex(BrokerError,'already running'):
                self.review.locate_sensor_map('a'*32,observed['revision'],'b'*32,1)
        finally:self.review.work.release()

    def test_sensor_map_rechecks_each_raw_geometry_and_late_invalidation(self):
        for change,reason in (('reference-before','SAVED_RAW_SOURCE_CHANGED'),
                              ('reference-after','SAVED_RAW_SOURCE_CHANGED'),('query-after','SAVED_RAW_SOURCE_CHANGED'),
                              ('model-before','NOMINAL_SENSOR_GEOMETRY_CHANGED'),('model-after','NOMINAL_SENSOR_GEOMETRY_CHANGED'),
                              ('epoch','INVALIDATED_DURING')):
            review=RoomLocalizationReview(self.root,'default',evidence_loader=evidence)
            observed=review.observation_map('a'*32)
            if change=='reference-before':review.evidence_loader=lambda *a:{**evidence(*a),'source_revision':'changed'}
            if change=='model-before':
                old=review.geometry_loader;review.geometry_loader=lambda:{**old(),'revision':'changed'}
            def compute(*args):
                if change in ('reference-after','query-after'):
                    target='a'*32 if change=='reference-after' else 'b'*32
                    review.evidence_loader=lambda root,project,job:{**evidence(root,project,job),
                        'source_revision':'changed' if job==target else 'a'*64}
                if change=='model-after':
                    old=review.geometry_loader;review.geometry_loader=lambda:{**old(),'revision':'changed'}
                if change=='epoch':review.invalidate()
                return {'status':'SENSOR_MAP_GEOMETRIC_CANDIDATE'}
            with patch('twinpulse_app.room_localization_review.locate_in_sensor_map',side_effect=compute),self.subTest(change=change),self.assertRaisesRegex(BrokerError,reason):
                review.locate_sensor_map('a'*32,observed['revision'],'b'*32,1)
            self.assertIsNone(review.sensor_match);self.assertIsNone(review.localization.binding)

    def test_model_comparison_rechecks_room_raw_model_and_late_invalidation(self):
        for change,reason in (('room','ROOM_SOURCE_CHANGED'),('raw','SAVED_RAW_SOURCE_CHANGED'),
                              ('model','NOMINAL_SENSOR_GEOMETRY_CHANGED'),('epoch','INVALIDATED_DURING')):
            review=RoomLocalizationReview(self.root,'default',evidence_loader=evidence)
            observed=review.observation_map('a'*32)
            revision=self.revision
            if change=='room':revision='changed'
            if change=='raw':review.evidence_loader=lambda *a:{**evidence(*a),'source_revision':'changed'}
            if change=='model':
                old=review.geometry_loader;review.geometry_loader=lambda:{**old(),'revision':'changed'}
            if change=='epoch':
                def interrupted(*a):review.invalidate();return {'geometry_changed':False}
                context=patch('twinpulse_app.room_localization_review.compare_observation_model',side_effect=interrupted)
            else:context=patch('twinpulse_app.room_localization_review.compare_observation_model',return_value={'geometry_changed':False})
            with context,self.subTest(change=change),self.assertRaisesRegex(BrokerError,reason):
                review.compare_model(revision,'a'*32,observed['revision'])
            self.assertIsNone(review.localization.binding)

    def test_new_session_failure_never_retains_an_old_position(self):
        self.review.analyse(self.revision,'a'*32,0)
        with self.assertRaises(BrokerError):self.review.analyse(self.revision,'b'*32,8)
        self.assertIsNone(self.review.snapshot()['result']);self.assertIsNone(self.review.localization.binding)

    def test_rejected_goal_explains_fit_and_changed_geometry_invalidates(self):
        report=self.review.analyse(self.revision,'a'*32,0)
        self.assertFalse(report['goal_candidate_available'])
        with self.assertRaisesRegex(BrokerError,'LOCALIZATION_'+report['match']['status']):
            self.review.goal(self.revision,report['revision'],report['epoch'],[0,0])
        old_geometry=self.review.geometry_loader
        self.review.geometry_loader=lambda:{**old_geometry(),'revision':'changed'}
        with self.assertRaisesRegex(BrokerError,'NOMINAL_SENSOR_GEOMETRY_CHANGED'):
            self.review.goal(self.revision,report['revision'],report['epoch'],[0,0])
        self.assertIsNone(self.review.snapshot()['result'])

    def test_unique_candidate_converts_goal_but_never_creates_a_mission(self):
        # Explicit synthetic matcher response exercises product routing only.
        candidate={'status':'GEOMETRIC_CANDIDATE','pose':[.2,.3,.4],
                   'mean_error_m':.01,'inlier_fraction':1.,'alternative_margin_m':.1}
        with patch('twinpulse_app.room_localization_review.RoomMatcher.match',return_value=candidate):
            report=self.review.analyse(self.revision,'a'*32,0)
        mapped=self.review.goal(self.revision,report['revision'],report['epoch'],[0,0])
        self.assertIsNone(mapped['mission_request']);self.assertFalse(mapped['motion_authorized'])
        self.assertEqual(mapped['scope'],'SAVED_FRAME_ONLY_NOT_CURRENT_ROBOT')
        self.assertEqual(len(mapped['odom_goal_candidate_m']),2)
        self.review.invalidate()
        with self.assertRaises(BrokerError):
            self.review.goal(self.revision,report['revision'],report['epoch'],[0,0])

    def test_changed_room_at_goal_and_visual_returns_precise_error(self):
        report=self.review.analyse(self.revision,'a'*32,0)
        with self.assertRaisesRegex(BrokerError,'ROOM_SOURCE_CHANGED'):
            self.review.visual_descriptor('changed',report['revision'])
        self.assertIsNone(self.review.snapshot()['result'])
        report=self.review.analyse(self.revision,'a'*32,0)
        with self.assertRaisesRegex(BrokerError,'ROOM_SOURCE_CHANGED'):
            self.review.goal('changed',report['revision'],report['epoch'],[0,0])
        self.assertIsNone(self.review.localization.binding)

    def test_visual_descriptor_rejects_paths_and_modified_report(self):
        report=self.review.analyse(self.revision,'a'*32,0)
        descriptor=self.review.visual_descriptor(self.revision,report['revision'])
        path=self.root/'artifacts/room-localization-review'/(report['report_id']+'.json')
        body=json.loads(path.read_text());body['robot_pose_room_candidate']=[99,99,0]
        path.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError,'LOCALIZATION_VISUAL_HASH'):
            checked_localization_visual(descriptor,source()[0],root=self.root)
        with self.assertRaisesRegex(ValueError,'LOCALIZATION_VISUAL_DESCRIPTOR'):
            checked_localization_visual({'report_id':'../outside','revision':'a'*64},source()[0],root=self.root)

    def test_room_changed_project_mismatch_and_busy_are_explained(self):
        for revision in ('c'*64,):
            with self.assertRaisesRegex(BrokerError,'ROOM_SOURCE_CHANGED'):self.review.analyse(revision,'a'*32,0)
        other=RoomLocalizationReview(self.root,'other',evidence_loader=evidence)
        with self.assertRaisesRegex(BrokerError,'PROJECT_REQUIRED'):other.analyse(self.revision,'a'*32,0)
        self.review.work.acquire()
        try:
            with self.assertRaisesRegex(BrokerError,'already running'):self.review.analyse(self.revision,'a'*32,0)
        finally:self.review.work.release()

    def test_invalidation_during_computation_discards_late_result(self):
        def interrupted(root,project,job):
            self.review.invalidate();return evidence(root,project,job)
        self.review.evidence_loader=interrupted
        with self.assertRaisesRegex(BrokerError,'INVALIDATED_DURING'):self.review.analyse(self.revision,'a'*32,0)
        self.assertIsNone(self.review.snapshot()['result'])

    def test_authenticated_http_paths_and_no_automatic_motion(self):
        server=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*43,engine_bootstrap_secret='e'*43)
        server.room_localization=self.review;server.start();self.addCleanup(server.stop)
        def request(path,body,headers=None):
            req=Request(server.base_url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
            try:
                with urlopen(req,timeout=20) as response:return response.status,json.loads(response.read()),response.headers
            except HTTPError as exc:return exc.code,json.loads(exc.read()),exc.headers
        _,boot,h=request('/v1/bootstrap',{'role':'product','secret':'p'*43})
        auth={'Cookie':h['Set-Cookie'].split(';')[0],'X-TwinPulse-CSRF':boot['csrf_token']}
        status,_,_=request('/v1/product/room-localization/review',{'revision':self.revision,'job_id':'a'*32,'frame':0})
        self.assertNotEqual(status,200)
        status,report,_=request('/v1/product/room-localization/review',{'revision':self.revision,'job_id':'a'*32,'frame':0},auth)
        self.assertEqual(status,200,report);self.assertFalse(report['physical_demo_ready'])
        status,_,_=request('/v1/product/room-localization/observation-map',{'job_id':'a'*32})
        self.assertNotEqual(status,200)
        status,observed,_=request('/v1/product/room-localization/observation-map',{'job_id':'a'*32},auth)
        self.assertEqual(status,200,observed);self.assertFalse(observed['photo_geometry_used'])
        status,_,_=request('/v1/product/room-localization/compare-model',{'job_id':'a'*32,'revision':self.revision,'observation_revision':observed['revision']})
        self.assertNotEqual(status,200)
        status,comparison,_=request('/v1/product/room-localization/compare-model',{'job_id':'a'*32,'revision':self.revision,'observation_revision':observed['revision']},auth)
        self.assertEqual(status,200,comparison);self.assertFalse(comparison['geometry_changed'])
        status,_,_=request('/v1/product/room-localization/compare-model',{'job_id':'a'*32,'revision':self.revision,'observation_revision':observed['revision'],'goal':[0,0]},auth)
        self.assertEqual(status,400)
        status,_,_=request('/v1/product/room-localization/observation-map',{'job_id':'a'*32,'goal':[0,0]},auth)
        self.assertEqual(status,400)
        sensor_body={'job_id':'a'*32,'observation_revision':observed['revision'],'query_job_id':'b'*32,'frame':0}
        status,_,_=request('/v1/product/room-localization/sensor-map',sensor_body)
        self.assertNotEqual(status,200)
        status,_,_=request('/v1/product/room-localization/sensor-map',{**sensor_body,'goal':[0,0]},auth)
        self.assertEqual(status,400)
        # Real core rejects this one-scan fake, rather than creating a position.
        status,rejected,_=request('/v1/product/room-localization/sensor-map',sensor_body,auth)
        self.assertEqual(status,409);self.assertIn('QUERY_THREE_SCANS_REQUIRED',str(rejected))
        with patch('twinpulse_app.room_localization_review.locate_in_sensor_map',return_value={'motion_authorized':False,'physical_demo_ready':False}):
            status,located,_=request('/v1/product/room-localization/sensor-map',sensor_body,auth)
        self.assertEqual(status,200,located);self.assertFalse(located['motion_authorized'])
        self.assertEqual(located['observation_revision'],observed['revision'])
        status,state,_=request('/v1/product/room-localization/invalidate',{},auth)
        self.assertEqual(status,200);self.assertIsNone(state['result'])


if __name__=='__main__':unittest.main()
