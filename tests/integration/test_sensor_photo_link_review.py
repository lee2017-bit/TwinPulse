# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from unittest.mock import patch
from tests.integration import test_room_localization_review as fixtures
from packages.twinpulse_core.tests.test_sensor_photo_link import fixture
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.sensor_photo_link import link_sensor_to_photo as fit_link
from twinpulse_app.command_broker import BrokerError
from twinpulse_app import CommandBroker,LocalApiServer


class PhotoLinkReviewTests(unittest.TestCase):
    # Reuse the setup only, not inherited test methods in this module's run.
    setUp=fixtures.ReviewTests.setUp

    def setup_sensor(self):
        sensor,_,_,_=fixture();observed=self.review.observation_map('a'*32)
        sensor.update(revision='sensor',epoch=observed['epoch'],observation_revision=observed['revision'],
            job_id='a'*32,query_job_id='b'*32,reference_source_revision='a'*64,query_source_revision='a'*64,
            nominal_geometry_revision=observed['nominal_geometry_revision'],reference_map_revision='sensor-map')
        self.review.sensor_match=sensor
        return self.review.photo_link_context(self.revision,'sensor')

    def test_link_report_sources_hash_goal_and_invalidation(self):
        context=self.setup_sensor();_,_,pairs,_=fixture()
        # Explicit synthetic correspondence math tests App routing, not photo fit.
        core_fixture=fixture()
        with patch('twinpulse_app.room_localization_review.link_sensor_to_photo',side_effect=lambda *a:fit_link(*core_fixture[:3])):
            report=self.review.link_photo(self.revision,'sensor',context['revision'],pairs)
        self.assertFalse(report['motion_authorized']);self.assertIsNone(self.review.localization.binding)
        path=self.root/'artifacts/sensor-photo-link'/(report['report_id']+'.json')
        saved=json.loads(path.read_text());digest=saved.pop('revision');self.assertEqual(canonical_sha256(saved),digest)
        result=self.review.photo_link_goal(self.revision,report['revision'],[0,0])
        self.assertIsNone(result['mission_request']);self.assertEqual(result['scope'],'HISTORICAL_QUERY_ONLY_NOT_CURRENT_ROBOT')
        self.review.invalidate();self.assertIsNone(self.review.photo_link)
        with self.assertRaisesRegex(BrokerError,'CURRENT_REPORT'):self.review.photo_link_goal(self.revision,report['revision'],[0,0])

    def test_no_current_sensor_ambiguity_wrong_room_context_and_busy(self):
        with self.assertRaisesRegex(BrokerError,'CURRENT_SENSOR'):self.review.photo_link_context(self.revision,'old')
        context=self.setup_sensor()
        with self.assertRaisesRegex(BrokerError,'CONTEXT_CHANGED'):self.review.link_photo(self.revision,'sensor','old',[])
        with self.assertRaisesRegex(BrokerError,'ROOM_SOURCE_CHANGED'):self.review.photo_link_context('other','sensor')
        self.review.sensor_match['status']='AMBIGUOUS'
        with self.assertRaisesRegex(BrokerError,'NOT_UNIQUE'):self.review.photo_link_context(self.revision,'sensor')
        self.review.work.acquire()
        try:
            with self.assertRaisesRegex(BrokerError,'already running'):self.review.link_photo(self.revision,'sensor',context['revision'],[])
        finally:self.review.work.release()

    def test_changed_reference_query_model_and_late_epoch_reject(self):
        for change,reason in (('reference','SAVED_RAW_SOURCE_CHANGED'),('query','SAVED_RAW_SOURCE_CHANGED'),
                              ('model','NOMINAL_SENSOR_GEOMETRY_CHANGED'),('epoch','CURRENT_SENSOR')):
            context=self.setup_sensor();original_loader=self.review.evidence_loader;original_model=self.review.geometry_loader
            def calculate(*args):
                if change in ('reference','query'):
                    target='a'*32 if change=='reference' else 'b'*32
                    self.review.evidence_loader=lambda root,project,job:{**fixtures.evidence(root,project,job),'source_revision':'changed' if job==target else 'a'*64}
                elif change=='model':self.review.geometry_loader=lambda:{**original_model(),'revision':'changed'}
                else:self.review.invalidate()
                return {'motion_authorized':False}
            with patch('twinpulse_app.room_localization_review.link_sensor_to_photo',side_effect=calculate),self.subTest(change=change),self.assertRaisesRegex(BrokerError,reason):
                self.review.link_photo(self.revision,'sensor',context['revision'],[])
            self.assertIsNone(self.review.photo_link)
            self.review.evidence_loader=original_loader;self.review.geometry_loader=original_model

    def test_actual_core_rejects_wrong_identity_and_no_physical_binding(self):
        context=self.setup_sensor();pairs=[{'endpoint_index':i,'anchor_id':a['id'],'role':'fit' if i<3 else 'validation'} for i,a in enumerate(context['anchors'][:4])]
        # These four corners lie on one thin wall: fit conditioning or mismatch
        # must not manufacture a calibrated pose. User claims aren't a survey.
        report=self.review.link_photo(self.revision,'sensor',context['revision'],pairs)
        self.assertEqual(report['status'],'ANCHOR_MISMATCH');self.assertIsNone(report['sensor_pose_room_candidate'])
        self.assertIsNone(self.review.localization.binding)

    def test_authenticated_strict_http_context_link_and_goal_rejection(self):
        self.setup_sensor()
        server=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*43,engine_bootstrap_secret='e'*43)
        server.room_localization=self.review;server.start();self.addCleanup(server.stop)
        def post(path,body,headers=None):
            req=Request(server.base_url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
            try:
                with urlopen(req,timeout=20) as response:return response.status,json.loads(response.read()),response.headers
            except HTTPError as exc:return exc.code,json.loads(exc.read()),exc.headers
        _,boot,h=post('/v1/bootstrap',{'role':'product','secret':'p'*43})
        auth={'Cookie':h['Set-Cookie'].split(';')[0],'X-TwinPulse-CSRF':boot['csrf_token']}
        path='/v1/product/room-localization/'
        body={'revision':self.revision,'sensor_revision':'sensor'}
        self.assertNotEqual(post(path+'photo-link-context',body)[0],200)
        self.assertEqual(post(path+'photo-link-context',{**body,'motion':True},auth)[0],400)
        status,context,_=post(path+'photo-link-context',body,auth);self.assertEqual(status,200,context)
        pairs=[{'endpoint_index':i,'anchor_id':a['id'],'role':'fit' if i<3 else 'validation'} for i,a in enumerate(context['anchors'][:4])]
        request={**body,'context_revision':context['revision'],'pairs':pairs}
        self.assertNotEqual(post(path+'photo-link',request)[0],200)
        self.assertEqual(post(path+'photo-link',{**request,'scale':2},auth)[0],400)
        status,report,_=post(path+'photo-link',request,auth);self.assertEqual(status,200,report)
        self.assertEqual(report['status'],'ANCHOR_MISMATCH');self.assertFalse(report['motion_authorized'])
        goal={'revision':self.revision,'link_revision':report['revision'],'goal':[0,0]}
        self.assertNotEqual(post(path+'photo-link-goal',goal)[0],200)
        status,rejected,_=post(path+'photo-link-goal',goal,auth)
        self.assertEqual(status,409);self.assertIn('LINK_ANCHORS_NOT_CONSISTENT',str(rejected))
