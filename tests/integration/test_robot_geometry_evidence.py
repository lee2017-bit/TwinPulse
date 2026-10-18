# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import unittest
from unittest.mock import patch
from tests.integration import test_bedroom_review as review_tests
from twinpulse_app.robot_geometry_evidence import load_geometry_evidence,origin,transformed
from twinpulse_app.command_broker import BrokerError


class GeometryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.evidence=load_geometry_evidence()
    def test_pinned_nominal_values_and_saved_raw_no_tf(self):
        e=self.evidence
        self.assertEqual(e['base_link_to_scan_xyz_m'],[-.032,0.,.172])
        self.assertEqual(e['base_footprint_to_base_link_xyz_m'],[0.,0.,.01])
        self.assertEqual(e['wheel_separation_m'],.16);self.assertEqual(e['wheel_radius_m'],.033)
        self.assertAlmostEqual(e['collision_aabb_base_link_m'][0][0],-.102)
        self.assertAlmostEqual(e['collision_aabb_base_link_m'][1][1],.0890262759)
        self.assertGreater(e['nominal_envelope_radius_m'],.12)
        self.assertEqual(e['retained_guard_radius_m'],.18)
        self.assertEqual(e['saved_scan']['frames'],74);self.assertIsNone(e['saved_scan']['odom_pose'])
        self.assertIsNone(e['saved_scan']['sensor_to_base_tf']);self.assertFalse(e['motion_authorized'])
        self.assertGreaterEqual(len(e['source_sha256']),9)
    def test_changed_pinned_model_is_rejected(self):
        with patch('twinpulse_app.robot_geometry_evidence.URDF_SHA','0'*64),self.assertRaises(ValueError):load_geometry_evidence()
    def test_cached_geometry_still_checks_current_mesh_bytes_and_keeps_identical_report(self):
        self.assertEqual(load_geometry_evidence(),self.evidence)
        with patch.dict('twinpulse_app.robot_geometry_evidence.MESH_HASHES',{'meshes/bases/burger_base.stl':'0'*64}):
            with self.assertRaisesRegex(ValueError,'MODEL_MESH_CHANGED'):load_geometry_evidence()
    def test_existing_review_goal_path_is_non_mutating_and_bound(self):
        fixture=review_tests.BedroomReviewTests();fixture.setUp();review=fixture.review;prepared=review.prepare()
        before=copy.deepcopy(fixture.source[0].to_dict());ev=self.evidence
        with patch.object(review,'geometry_evidence',return_value=ev):
            result=review.goal_preview(prepared['revision'],ev['revision'],[0.,0.],None)
            self.assertIsNone(result['mission_request']);self.assertIsNone(result['odom_goal_candidate_m'])
            reference={'schema':'twin-odom-reference-1.0','scene_revision':prepared['scene_revision'],
                'evidence_revision':ev['revision'],'boot_id':'synthetic','basis':'synthetic_test_fixture',
                'pairs':[{'twin_xy_m':p,'odom_xy_m':[1-p[1],2+p[0]]} for p in ([0.,0.],[1.,0.],[0.,1.])]}
            result=review.goal_preview(prepared['revision'],ev['revision'],[.2,.3],reference)
            self.assertAlmostEqual(result['odom_goal_candidate_m'][0],.7);self.assertFalse(result['motion_authorized'])
            for revision,evidence,goal in [('bad',ev['revision'],[0,0]),(prepared['revision'],'bad',[0,0]),
                                          (prepared['revision'],ev['revision'],[2,0])]:
                with self.assertRaises(BrokerError):review.goal_preview(revision,evidence,goal,reference)
        self.assertEqual(fixture.source[0].to_dict(),before)
