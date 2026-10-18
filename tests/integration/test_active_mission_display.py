# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned active display access/expiry; no robot or renderer success injection."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from packages.twinpulse_core.tests.test_active_mission_visual import frame


class ActiveDisplayTests(unittest.TestCase):
    def test_native_and_app_job_binding_is_derived_without_rewriting_raw_visual(self):
        from copy import deepcopy
        from twinpulse_core.revisions import canonical_sha256
        with TemporaryDirectory() as td:
            automatic=AutomaticDemoService(Path(td),'room');service=AutomaticMissionService(automatic,clock=lambda:10.)
            self.addCleanup(automatic.close);self.addCleanup(service.close)
            sample=frame();native='b'*32;raw=deepcopy(sample['visual'])
            raw['session_id']=native;raw['revision']=canonical_sha256({k:v for k,v in raw.items() if k!='revision'})
            service.worker=SimpleNamespace(is_alive=lambda:True)
            service.job={'owner':'owner','job_id':sample['job_id'],'native_mission_id':native,
                'objects_revision':sample['objects_revision'],'visual':deepcopy(raw),'visual_sequence':1,'visual_updated_s':10.}
            display=service.active_visual('engine','epoch',sample['objects_revision'])['frame']
            self.assertEqual(display['visual']['session_id'],sample['job_id'])
            self.assertEqual(service.job['visual'],raw)
            self.assertEqual(service.job['native_visual_binding']['native_visual_revision'],raw['revision'])
            service.job['native_mission_id']='c'*32
            with self.assertRaisesRegex(ValueError,'MISSION_NATIVE_VISUAL_IDENTITY_CHANGED'):
                service.active_visual('engine','epoch',sample['objects_revision'])
            service.worker=None;service.job=None
    def test_owned_correction_negotiates_geometry_only_then_fresh_frame_or_typed_failure(self):
        with TemporaryDirectory() as td:
            clock=[10.];automatic=AutomaticDemoService(Path(td),'room')
            service=AutomaticMissionService(automatic,clock=lambda:clock[0]);sample=frame()
            service.worker=SimpleNamespace(is_alive=lambda:True)
            service.job={'owner':'owner','job_id':sample['job_id'],'objects_revision':sample['objects_revision'],
                'visual':sample['visual'],'visual_sequence':2,'visual_updated_s':10.,'started':10.,
                'original_goal':{'room_revision':'c'*64},'photo_correction':{'applied_revision':'d'*64,
                    'goal_revalidation':'NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED','isaac_geometry_status':'PENDING'}}
            result=service.active_visual('engine','epoch','c'*64)
            self.assertIsNone(result['frame']);self.assertEqual(result['geometry']['objects_revision'],'b'*64)
            self.assertEqual(service.active_visual('engine','epoch','e'*64)['code'],'ISAAC_ROOM_GEOMETRY_CHANGED')
            for fault,expected in (('stop','NO_ACTIVE_MISSION'),('pose','CURRENT_ROOM_POSE_UNAVAILABLE'),('stale','ACTIVE_VISUAL_STALE')):
                if fault=='stop':service.stop_action='stop'
                elif fault=='pose':service.job['visual']['pose_room']=None
                else:clock[0]=11.
                self.assertEqual(service.active_visual('engine','epoch','c'*64)['code'],expected)
                service.stop_action=None;service.job['visual']['pose_room']=[0.,0.,0.];clock[0]=10.
            receipt={'job_id':sample['job_id'],'sequence':2,'status':'ACTIVE_GEOMETRY_RENDER_FAILED',
                     'error_code':'ACTIVE_GEOMETRY_PERMIT_EXPIRED','error_type':'ValueError'}
            self.assertEqual(service.active_visual('engine','epoch','c'*64,receipt)['code'],'ACTIVE_GEOMETRY_RENDER_FAILED')
            self.assertNotIn('geometry',service.active_visual('engine','epoch','c'*64))
            self.assertEqual(service.job['photo_correction']['error_code'],receipt['error_code'])
            # Separate successful receipt contract, not an injected renderer runtime PASS.
            service.job['photo_correction']={'applied_revision':'d'*64,'goal_revalidation':'NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED'}
            ack={k:v for k,v in receipt.items() if k not in {'error_code','error_type'}}
            ack['status']='ACTIVE_GEOMETRY_COMPOSED_NOT_CURRENT'
            self.assertIsNotNone(service.active_visual('engine','epoch','b'*64,ack)['frame'])
            self.assertEqual(service.job['photo_correction']['isaac_geometry_status'],'OWNED_ISAAC_GEOMETRY_COMPOSED')
            self.assertEqual(service.active_visual('engine','epoch','b'*64,receipt)['code'],'ACTIVE_GEOMETRY_RENDER_FAILED')
            self.assertIsNone(service.active_visual('engine','epoch','b'*64)['frame'])
            self.assertEqual(service.job['photo_correction']['error_code'],receipt['error_code'])
            service.job=None;service.worker=None;service.close();automatic.close()

    def test_localizing_remote_visual_cannot_freshen_a_previous_pose(self):
        with TemporaryDirectory() as td:
            automatic=AutomaticDemoService(Path(td),'room');service=AutomaticMissionService(automatic,clock=lambda:10.)
            sample=frame();sample['visual']['state']='LOCALIZING'
            service.worker=SimpleNamespace(is_alive=lambda:True)
            service.job={'owner':'owner','job_id':sample['job_id'],'objects_revision':sample['objects_revision'],
                'visual':sample['visual'],'visual_sequence':2,'visual_updated_s':10.,'started':10.,
                'isaac_display':{'status':'ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED','received_s':10.}}
            self.assertEqual(service.active_visual('engine','epoch',sample['objects_revision'])['code'],'CURRENT_ROOM_POSE_UNAVAILABLE')
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],'CURRENT_ROOM_POSE_UNAVAILABLE')
            service.job=None;service.worker=None;service.close();automatic.close()

    def test_engine_poll_does_not_extend_owner_presence_and_wrong_room_cannot_read_pose(self):
        with TemporaryDirectory() as td:
            clock=[10.];automatic=AutomaticDemoService(Path(td),'room')
            service=AutomaticMissionService(automatic,clock=lambda:clock[0])
            sample=frame();service.worker=SimpleNamespace(is_alive=lambda:True)
            service.job={'owner':'owner','job_id':sample['job_id'],'objects_revision':sample['objects_revision'],
                'visual':sample['visual'],'visual_sequence':1,'visual_updated_s':10.,'started':10.}
            clock[0]=10.1;presence=service.last_owner_presence
            self.assertEqual(service.active_visual('engine','epoch','c'*64)['code'],'ISAAC_ROOM_GEOMETRY_CHANGED')
            self.assertEqual(service.active_visual('engine','epoch',sample['objects_revision'])['frame'],sample)
            self.assertEqual(service.last_owner_presence,presence)
            receipt={'job_id':sample['job_id'],'sequence':1,'status':'ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED'}
            service.active_visual('engine','epoch',sample['objects_revision'],receipt)
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],receipt['status'])
            service.active_visual('engine','epoch',sample['objects_revision'],{**receipt,'job_id':'b'*32,'status':'ACTIVE_VISUAL_RENDER_FAILED'})
            self.assertEqual(service.job['isaac_display']['status'],receipt['status'])
            clock[0]=11.
            self.assertEqual(service.active_visual('engine','epoch',sample['objects_revision'],receipt)['code'],'ACTIVE_VISUAL_STALE')
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],'ACTIVE_VISUAL_STALE')
            service.worker=SimpleNamespace(is_alive=lambda:False)
            self.assertIsNone(service.active_visual('engine','epoch',sample['objects_revision'],receipt)['frame'])
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],'NO_ACTIVE_MISSION')
            service.job=None;service.worker=None;service.close();automatic.close()

    def test_duplicate_renderer_receipt_is_not_new_render_evidence(self):
        with TemporaryDirectory() as td:
            clock=[10.];automatic=AutomaticDemoService(Path(td),'room')
            service=AutomaticMissionService(automatic,clock=lambda:clock[0]);sample=frame()
            service.worker=SimpleNamespace(is_alive=lambda:True)
            service.job={'owner':'owner','job_id':sample['job_id'],'objects_revision':sample['objects_revision'],
                'visual':sample['visual'],'visual_sequence':1,'visual_updated_s':10.,'started':10.}
            receipt={'job_id':sample['job_id'],'sequence':1,'status':'ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED'}
            service.active_visual('engine','epoch',sample['objects_revision'],receipt)
            clock[0]=11.;service.job.update(visual_sequence=2,visual_updated_s=11.)
            service.active_visual('engine','epoch',sample['objects_revision'],receipt)
            self.assertEqual(service.job['isaac_display']['received_s'],10.)
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],'ACTIVE_VISUAL_STALE')
            service.active_visual('engine','epoch',sample['objects_revision'],{**receipt,'sequence':2})
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],receipt['status'])
            service.job['visual']['pose_room']=None
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],'CURRENT_ROOM_POSE_UNAVAILABLE')
            service.job['visual']['pose_room']=[0.,0.,0.];service.job['state']='MISSION_ARRIVED'
            self.assertEqual(service.active_visual('engine','epoch',sample['objects_revision'],{**receipt,'sequence':2})['code'],'NO_ACTIVE_MISSION')
            self.assertEqual(service.snapshot('owner')['job']['isaac_display']['status'],'NO_ACTIVE_MISSION')
            service.job=None;service.worker=None;service.close();automatic.close()
