# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Component-only innovation filtering; product raycaster tests are separate."""
import math
import unittest
from unittest.mock import patch

from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.local_navigation import LocalPose,LocalScan
from twinpulse_core.room_localization import compose,angle
from packages.twinpulse_core.tests.test_room_localization import fixture,scan_points


class CurrentInnovationTests(unittest.TestCase):
    def tracker(self):
        points=scan_points(fixture(),[0.,0.,0.],beam_count=120)
        tracker=CurrentMissionEvidence({'schema':'session-survey-map-1.0','endpoint_cells':points,
            'tracking_endpoints':points,'tracking_endpoint_basis':'ACCEPTED_SURVEY_DESKEWED_RETURNS_ODOMETRY_PROJECTED'},
            {'room_from_map':[0.,0.,0.],'report_revision':'d'*64,'status':'ALIGNMENT_CANDIDATE'},
            {'project_id':'test','source_revision':'b'*64,'epoch':1},'c'*64)
        tracker.transform=[0.,0.,0.]
        return tracker,points

    def test_persisted_cell_reference_keeps_original_single_innovation(self):
        _,points=self.tracker()
        tracker=CurrentMissionEvidence({'endpoint_cells':points},
            {'room_from_map':[0.,0.,0.],'report_revision':'d'*64,'status':'ALIGNMENT_CANDIDATE'},
            {'project_id':'test','source_revision':'b'*64,'epoch':1},'c'*64)
        tracker.transform=[0.,0.,0.]
        for i,proposal in enumerate((.02,-.02,.02)):
            before=tracker.transform[0]
            value=self.tick(tracker,points,[i*.03,0.,0.],[proposal,0.,0.],20+i*.05)
            expected=before+max(-.0025,min(.0025,.15*(proposal-before)))
            self.assertAlmostEqual(tracker.transform[0],expected)
            self.assertNotIn('innovation_basis',value['match'])
            self.assertFalse(tracker.innovations)

    def tick(self,tracker,points,odom,proposal,now,status='TRACKING_CANDIDATE'):
        pose=LocalPose(tuple(odom),now,'test','synthetic_model','synthetic_raycast')
        match={'status':status,'pose':compose(proposal,odom) if proposal is not None else None}
        with patch('twinpulse_core.current_mission_evidence.local_match',return_value=match):
            return tracker._update_points(pose,points,[[0.,0.]]*len(points),now,now)

    def test_alternating_transform_noise_damped_without_lagging_odom_motion(self):
        tracker,points=self.tracker()
        for i in range(12):
            odom=[i*.03,0.,0.]
            value=self.tick(tracker,points,odom,[.02 if i%2==0 else -.02,0.,0.],20+i*.05)
            self.assertLessEqual(abs(value['pose_map'][0]-odom[0]),.003)
            self.assertLessEqual(value['match']['innovation_sample_count'],4)
            self.assertFalse(value['motion_authorized'])
        self.assertLess(abs(tracker.transform[0]),.001)
        self.assertGreater(value['pose_map'][0],.329)

    def test_expired_or_rejected_history_never_becomes_current_pose(self):
        tracker,points=self.tracker()
        self.tick(tracker,points,[0.,0.,0.],[.02,0.,0.],20.)
        value=self.tick(tracker,points,[0.,0.,0.],[-.02,0.,0.],20.25)
        self.assertEqual(value['match']['innovation_sample_count'],1)
        lost=self.tick(tracker,points,[0.,0.,0.],None,20.30,'AMBIGUOUS')
        self.assertIsNone(lost['pose_map']);self.assertEqual(lost['scan_room'],[])
        self.assertEqual(lost['cells'],[]);self.assertFalse(tracker.innovations)
        tracker.transform=[0.,0.,0.]
        value=self.tick(tracker,points,[0.,0.,0.],[.02,0.,0.],20.35)
        self.assertEqual(value['match']['innovation_sample_count'],1)
        scan=LocalScan(tuple([1.]*120),20.,'base_link','synthetic_model','synthetic_raycast')
        pose=LocalPose((0.,0.,0.),20.35,'test','synthetic_model','synthetic_raycast')
        with self.assertRaisesRegex(ValueError,'MISSION_CURRENT_SENSOR_INVALID'):
            tracker.update(pose,scan,20.35)
        self.assertIsNone(tracker.transform);self.assertFalse(tracker.innovations)

    def test_wraparound_yaw_and_innovation_cap_are_preserved(self):
        tracker,points=self.tracker();tracker.transform=[0.,0.,math.pi-.001]
        for i in range(4):
            before=list(tracker.transform)
            value=self.tick(tracker,points,[0.,0.,.1*i],[.1,0.,-math.pi+.001],20+i*.05)
            self.assertLessEqual(abs(tracker.transform[0]-before[0]),.002500001)
            self.assertLessEqual(abs(angle(tracker.transform[2]-before[2])),.002500001)
            self.assertLess(abs(angle(tracker.transform[2]-math.pi)),.003)
            self.assertTrue(all(math.isfinite(v) for v in value['pose_map']))


if __name__=='__main__':unittest.main()
