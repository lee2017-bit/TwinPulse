# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded display contracts, never physical or USD acceptance."""
import copy
import unittest
from twinpulse_core.active_mission_visual import checked_active_frame,checked_display_result,checked_active_geometry
from twinpulse_core.revisions import canonical_sha256


def frame():
    visual={'schema':'automatic-mission-visual-1.0','session_id':'a'*32,
        'context':{'project_id':'room','source_revision':'b'*64,'epoch':1},'state':'DRIVING',
        'room_revision':'c'*64,'route_revision':'d'*64,'map_revision':'e'*64,'alignment_revision':'f'*64,
        'pose_room':[0.,0.,0.],'goal_room':[.3,0.],'route_room':[[.3,0.]],'scan_room':[[1.,1.]],
        'trajectory_room':[[0.,0.,0.]],'motion_authorized':False,'physical_demo_ready':False,'provenance':'synthetic_raycast'}
    body={'schema':'active-mission-frame-1.0','engine_session_id':'engine','stage_epoch':'epoch','project_id':'room',
        'objects_revision':'b'*64,'job_id':'a'*32,'sequence':1,'visual':{**visual,'revision':canonical_sha256(visual)}}
    return {**body,'revision':canonical_sha256(body)}


def rehash(value):
    value['visual']['revision']=canonical_sha256({k:v for k,v in value['visual'].items() if k!='revision'})
    value['revision']=canonical_sha256({k:v for k,v in value.items() if k!='revision'})
    return value


class ActiveVisualTests(unittest.TestCase):
    def test_geometry_permission_is_hash_bound_and_carries_no_pose_or_authority(self):
        body={'schema':'active-mission-geometry-1.0','engine_session_id':'engine','stage_epoch':'epoch',
              'project_id':'room','job_id':'a'*32,'sequence':2,'previous_objects_revision':'c'*64,
              'objects_revision':'b'*64,'correction_revision':'d'*64}
        good={**body,'revision':canonical_sha256(body)}
        self.assertEqual(checked_active_geometry(good),good)
        for patch in ({'pose_room':[0,0,0]},{'motion_authorized':False},{'sequence':True},
                      {'previous_objects_revision':'b'*64},{'project_id':'../room'},{'objects_revision':'e'*64}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):checked_active_geometry({**good,**patch})
        receipt={'job_id':'a'*32,'sequence':2,'status':'ACTIVE_GEOMETRY_RENDER_FAILED',
                 'error_code':'PHOTO_LEDGER_HEAD_CHANGED','error_type':'ValueError'}
        self.assertEqual(checked_display_result(receipt),receipt)
        for patch in ({'status':'NO_ACTIVE_MISSION'},{'error_code':'private/path'},{'error_type':'secret text'}, {'error_text':'raw'}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):checked_display_result({**receipt,**patch})

    def test_exact_hash_source_and_no_authority(self):
        self.assertEqual(checked_active_frame(frame()),frame())
        for change in ('authority','project','old_source','extra','revision','context','missing_room','oversize','lost_position'):
            with self.subTest(fault=change):
                bad=copy.deepcopy(frame())
                if change=='authority':bad['visual']['motion_authorized']=True
                if change=='project':bad['visual']['context']['project_id']='other'
                if change=='old_source':bad['visual']['provenance']='saved_sensor_recording'
                if change=='extra':bad['visual']['context']['position_is_verified']=True
                if change=='context':bad['visual']['context']['epoch']=True
                if change=='missing_room':bad['visual']['room_revision']=None
                if change=='oversize':bad['visual']['scan_room']=[[1.,1.]]*161
                if change=='lost_position':bad['visual']['state']='LOCALIZING'
                if change!='revision':rehash(bad)
                else:bad['visual']['pose_room'][0]=.1
                with self.assertRaises(ValueError):checked_active_frame(bad)
    def test_live_context_and_typed_renderer_receipt(self):
        value=frame();value['visual']['provenance']='live_sensor'
        value['visual']['context']={'project_id':'room','session_id':'live','boot_id':'boot','release_id':'b'*64,
            'source_revision':'b'*64,'origin':'live_ros'}
        checked_active_frame(rehash(value))
        value['visual']['context']['origin']='recorded_ros'
        with self.assertRaises(ValueError):checked_active_frame(rehash(value))
        self.assertIsNone(checked_display_result(None))
        good={'job_id':'a'*32,'sequence':1,'status':'ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED'}
        self.assertEqual(checked_display_result(good),good)
        for bad in ({**good,'status':'SUCCESS_PHYSICAL'},{**good,'sequence':True},{**good,'extra':1}):
            with self.assertRaises(ValueError):checked_display_result(bad)
