# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from twinpulse_core.room_goal import room_goal_preview


class RoomGoalTests(unittest.TestCase):
    def reference(self):
        return {'schema':'twin-odom-reference-1.0','scene_revision':'a'*64,'evidence_revision':'b'*64,
            'boot_id':'test-boot','basis':'synthetic_test_fixture','pairs':[
                {'twin_xy_m':p,'odom_xy_m':[1-p[1],2+p[0]]} for p in ([0.,0.],[1.,0.],[0.,1.]) ]}
    def run_preview(self,reference,goal=None):
        return room_goal_preview(goal or [.2,.3],reference,scene_revision='a'*64,evidence_revision='b'*64)
    def test_no_reference_never_invents_coordinates(self):
        result=self.run_preview(None)
        self.assertIsNone(result['odom_goal_candidate_m']);self.assertFalse(result['motion_authorized'])
    def test_rigid_direction_correct_and_no_authority(self):
        reference=self.reference();before=copy.deepcopy(reference);result=self.run_preview(reference)
        for a,b in zip(result['odom_goal_candidate_m'],[.7,2.2]):self.assertAlmostEqual(a,b)
        self.assertAlmostEqual(result['twin_to_odom_candidate']['yaw_rad'],math.pi/2)
        self.assertLess(result['max_residual_m'],1e-12);self.assertEqual(reference,before)
        for key in ('alignment_verified','motion_authorized','reference_verified','current_boot_verified'):
            self.assertFalse(result[key])
    def test_context_and_photographic_guesses_rejected(self):
        for change in ({'scene_revision':'c'*64},{'evidence_revision':'c'*64},{'basis':'photo'},
                       {'boot_id':''},{'motion_authorized':True},{'schema':'other'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.run_preview({**self.reference(),**change})
    def test_degenerate_duplicate_and_too_few(self):
        for points in ([[0,0],[1,0]],[[0,0],[1,0],[2,0]],[[0,0],[1,0],[1,0]]):
            reference=self.reference();reference['pairs']=[{'twin_xy_m':p,'odom_xy_m':p} for p in points]
            with self.assertRaises(ValueError):self.run_preview(reference)
    def test_reflection_scale_and_inconsistent_distances_rejected(self):
        for transform in (lambda p:[p[0],-p[1]],lambda p:[2*p[0],2*p[1]],lambda p:[p[0]+p[1],p[1]]):
            reference=self.reference()
            for pair in reference['pairs']:pair['odom_xy_m']=transform(pair['twin_xy_m'])
            with self.assertRaises(ValueError):self.run_preview(reference)
    def test_numbers_and_unknown_pair_fields_rejected(self):
        for goal in ([True,0],[math.nan,0],[math.inf,0],[0],[0,0,0],['1',0]):
            with self.assertRaises(ValueError):self.run_preview(self.reference(),goal)
        reference=self.reference();reference['pairs'][0]['label']='anything'
        with self.assertRaises(ValueError):self.run_preview(reference)
    def test_unbounded_mission_coordinate_rejected(self):
        with self.assertRaises(ValueError):self.run_preview(self.reference(),[20,0])
