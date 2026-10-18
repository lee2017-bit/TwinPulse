# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Accepted survey -> reference -> new sensor localization, offline only."""
from copy import deepcopy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from twinpulse_app.survey_reference import reference_key,reference_descriptor,load_survey_reference
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.chat_inspection_visual import KIND,load_current_source
from twinpulse_app.remote_observed_adapter import RemoteObservedFactory
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.local_navigation import LocalPose,LocalScan
from twinpulse_core.revisions import canonical_sha256
from tests.integration.test_cold_start_mission import ColdStartTests
from tests.integration.test_automatic_demo_service import GEOMETRY
from tests.integration.test_automatic_mission_service import RaycastAdapter
from packages.twinpulse_core.tests.test_room_localization import scan_points


class SurveyReferenceTests(unittest.TestCase):
    setUp=ColdStartTests.setUp
    execute=ColdStartTests.execute

    def capture(self):
        job,adapter,report=self.execute('reference_room',1.,[0.,-.6,0.],[0.,0.],
            mode='SURVEY_ONLY',photo_policy='correct_walls',current_chat=True)
        self.assertEqual(job['state'],'MISSION_ARRIVED',job.get('error'))
        self.path=self.root/'artifacts/automatic-mission/reference_room'/f"{job['job_id']}.json"
        self.original=self.path.read_bytes()
        self.key=reference_key({'kind':KIND,'mission_id':job['job_id'],'manifest_sha256':job['report_revision']})
        return report,adapter

    def load(self,key=None):
        return load_survey_reference(self.root,'reference_room',key or self.key,
            current_source=load_current_source(self.root,'reference_room'))

    def replace_report(self,report):
        report=deepcopy(report);report['revision']=canonical_sha256({k:v for k,v in report.items() if k!='revision'})
        self.path.write_text(json.dumps(report),encoding='utf-8')
        return reference_key({'kind':KIND,'mission_id':report['job_id'],'manifest_sha256':report['revision']})

    def test_full_reference_reopen_moved_start_and_actual_shared_loop(self):
        report,adapter=self.capture();prior=self.load()
        self.assertEqual(prior['map'],report['survey_map'])
        alignment=prior['photo_alignment']
        self.assertEqual(alignment['source_report_revision'],report['photo_alignment']['report_revision'])
        self.assertEqual(alignment['report_revision'],canonical_sha256({k:v for k,v in alignment.items() if k!='report_revision'}))
        self.assertGreater(len(prior['map']['tracking_endpoints']),160)
        self.assertIsNone(prior['pose_candidate']);self.assertFalse(prior['motion_authorized'])
        automatic=AutomaticDemoService(self.root,'reference_room',geometry_loader=lambda:GEOMETRY,
            room_loader=lambda root,pid:load_current_source(root,pid)['room'])
        automatic.room_scene_loader=lambda root,pid:load_current_source(root,pid)['scene']
        self.addCleanup(automatic.close)
        service=AutomaticMissionService(automatic);self.addCleanup(service.close)
        goal={'mode':'NAVIGATE_TWIN_GOAL','xy':[.15,-.6],
            'room_revision':report['goal']['room_revision'],'duration_s':45.}
        self.assertEqual(service._prior(self.key,goal)[0],prior)
        # Current scan/odom matching from a manually changed start, not report
        # pose or world-truth injection into the matcher.
        start=[-.1,-.6,.1]
        def factory(p,room,effective,g):
            self.live=RaycastAdapter(p,room,effective,g,outline=adapter.outline,start=start)
            return self.live
        service.adapter_factory=factory;service.start('owner',self.key,goal)
        service.worker.join(30);self.assertFalse(service.worker.is_alive())
        result=service.snapshot('owner')['job']
        self.assertEqual(result['state'],'MISSION_ARRIVED',result.get('error'))
        self.assertLess(math.dist(self.live.world[:2],goal['xy']),.1)
        self.assertEqual(self.live.velocity,(0.,0.));self.assertEqual(self.live.consumed,1)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertFalse(result['physical_demo_ready'])
        # Remote full handoff is explicit, not a silently truncated reference.
        room=automatic.room_loader(self.root,'reference_room');effective=automatic.photo_store.current(room)
        remote=RemoteObservedFactory(None,self.root,'reference_room')
        with self.assertRaisesRegex(ValueError,'SURVEY_REFERENCE_REMOTE_FULL_HANDOFF_REQUIRED'):
            remote(prior,room,effective,goal)
        # The selected reference survives a completed goal, but remains owned
        # and is checked afresh against room/report/ledger on every request.
        from twinpulse_app.chat_inspection import ChatInspection
        inspection=ChatInspection(service,None,None,None)
        inspection.owner='owner';inspection.job_id=report['job_id']
        inspection.reference_descriptor=reference_descriptor(self.key)
        self.assertEqual(inspection.reference('owner'),self.key)
        with self.assertRaises(BrokerError):inspection.reference('other')

    def test_actual_reference_bound_to_registered_goal_source_not_adapter_choice(self):
        report,_=self.capture();prior=self.load()
        automatic=AutomaticDemoService(self.root,'reference_room',geometry_loader=lambda:GEOMETRY,
            room_loader=lambda root,pid:load_current_source(root,pid)['room'])
        automatic.room_scene_loader=lambda root,pid:load_current_source(root,pid)['scene']
        self.addCleanup(automatic.close)
        from tests.integration.test_current_goal_preview import evidence
        from twinpulse_app.chat_inspection_visual import derived_scene
        from twinpulse_core.site_contracts import SceneRevision
        from twinpulse_core.room_localization import compose,inverse
        self.current=evidence();self.current['project_id']='reference_room'
        self.current['room_revision']=report['goal']['room_revision']
        self.current['alignment_revision']=prior['photo_alignment']['report_revision']
        self.current['room_from_map']=prior['photo_alignment']['room_from_map']
        self.current['pose_map']=compose(inverse(self.current['room_from_map']),[0.,-.6,0.])
        self.map_key=self.key;reads=[]
        class Source:
            supports_current_goal_preview=True
            clock=staticmethod(lambda:1.)
            def preview_current(inner,owner,*,reference_key=None):
                reads.append((owner,reference_key))
                return {'map_id':self.map_key,'evidence':deepcopy(self.current),
                    'context':{k:self.current[k] for k in ('project_id','source_revision','epoch')}}
        service=AutomaticMissionService(automatic,adapter_factory=Source());self.addCleanup(service.close)
        room=automatic.room_loader(self.root,'reference_room');effective=automatic.photo_store.current(room)
        source=SceneRevision.from_dict(automatic.room_scene_loader(self.root,'reference_room'))
        scene=derived_scene(source,effective)
        review=service.preview_goal('owner',scene,'Go x=.15 y=-.6',reference_key=self.key)
        self.assertEqual(review['map_id'],self.key);self.assertIsNotNone(review['plan'])
        self.assertEqual(reads,[('owner',self.key)]);self.assertIsNone(service.worker)
        self.map_key='unrelated-map'
        with self.assertRaisesRegex(BrokerError,'REFERENCE_CHANGED'):
            service.preview_goal('owner',scene,'Go x=.15 y=-.6',reference_key=self.key)
        self.map_key=self.key;self.current['alignment_revision']='a'*64
        with self.assertRaisesRegex(BrokerError,'REFERENCE_ALIGNMENT_CHANGED'):
            service.preview_goal('owner',scene,'Go x=.15 y=-.6',reference_key=self.key)
        self.assertIsNone(service.worker);self.assertEqual(self.path.read_bytes(),self.original)

    def test_tamper_failed_raw_missing_fit_and_current_ledger_rejected(self):
        report,_=self.capture();self.assertEqual(self.load()['map']['revision'],report['survey_map']['revision'])
        for fault in ('tamper','failed','missing','fit','keyframe','held','pose','geometry'):
            with self.subTest(fault=fault):
                bad=deepcopy(report)
                if fault=='tamper':bad['goal']['room_revision']='a'*64
                if fault=='failed':bad['state']='FAILED';bad['error']='ORIGINAL_FAILURE'
                if fault=='missing':bad.pop('survey_map')
                if fault=='fit':bad['photo_alignment']['source_map_revision']='a'*64
                if fault=='keyframe':bad['survey_map']['tracking_endpoints'][0][0]+=.01
                if fault=='held':bad['photo_alignment']['validation_sequences']=bad['photo_alignment']['fit_sequences']
                if fault=='pose':bad['photo_alignment']['room_from_map']=[float('nan'),0.,0.]
                if fault=='geometry':bad['photo_alignment']['corrected_objects'][0]['transform']['position_m'][0]+=.1
                if fault in {'held','geometry'}:
                    bad['photo_alignment']['report_revision']=canonical_sha256({k:v for k,v in bad['photo_alignment'].items() if k!='report_revision'})
                if fault=='pose':
                    with self.assertRaises(ValueError):self.replace_report(bad)
                    continue
                key=self.replace_report(bad)
                with self.assertRaises((ValueError,KeyError)):self.load(self.key if fault=='tamper' else key)
        self.path.write_bytes(self.original)
        from twinpulse_app.automatic_photo_store import AutomaticPhotoStore
        source=load_current_source(self.root,'reference_room');store=AutomaticPhotoStore(self.root,'reference_room')
        now=store.current(source['room'])
        store.append(source['room'],now['head'],now['events'][-1]['before_objects'],action='rollback',
            job_id='c'*32,map_revision=report['survey_map']['revision'])
        with self.assertRaisesRegex(ValueError,'LEDGER_CHANGED'):self.load()

    def test_opaque_key_has_no_path_and_wrong_project_or_digest_never_reopens(self):
        report,_=self.capture()
        for key in ('survey:../file','survey:'+'a'*32+':'+'b'*64+'x','file:///tmp/report'):
            with self.assertRaises(ValueError):reference_descriptor(key)
        bad=self.key[:-1]+('0' if self.key[-1]!='0' else '1')
        with self.assertRaisesRegex(ValueError,'HASH_CHANGED'):self.load(bad)
        with self.assertRaises(ValueError):load_survey_reference(self.root,'other',self.key)
        self.assertEqual(self.path.read_bytes(),self.original)
