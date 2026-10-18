# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from twinpulse_core.observation_model_comparison import compare_observation_model
from twinpulse_core.room_localization import compose


def obj(name,kind,p,d):
    return {'id':name,'kind':kind,'transform':{'position_m':p,'rotation_rpy_deg':[0,0,0]},'shape':{'dimensions_m':d}}


def objects():
    return [obj('floor','floor',[0,0,0],[8,8,.1]),obj('wall','wall',[0,3,1],[8,.1,2]),
            obj('table','box_obstacle',[0,1,.7],[1,1,.1]),obj('chair','box_obstacle',[1,1,.4],[.5,.5,.8])]


def observation():
    return {'coordinate_frame':'SESSION_START_ODOM_LOCAL_NOT_ROOM_OR_MAP',
            'keyframes':[{'frame':i*10,'elapsed_s':float(i),'sensor_pose':[float(i),0,0],
                          'points':[[2*math.cos(n*math.tau/32),2*math.sin(n*math.tau/32)] for n in range(32)]} for i in range(2)]}


class FixtureMatcher:
    def __init__(self,outline): pass
    def match(self,points):return {'status':'GEOMETRIC_CANDIDATE','pose':[2.,0,0]}
    def score(self,points,pose):return min(.5,abs(pose[0]-2)),1. if abs(pose[0]-2)<.1 else 0.
    def possible(self,pose):return True


class ComparisonTests(unittest.TestCase):
    def test_changed_coordinate_origin_and_heading_do_not_reuse_an_old_transform(self):
        original=observation();shifted=copy.deepcopy(original);change=[1.,-.5,.8]
        for key in shifted['keyframes']:
            key['sensor_pose']=compose(change,key['sensor_pose'])
            key['points']=[compose(change,[*p,0])[:2] for p in key['points']]
        a=compare_observation_model(original,objects(),.18,matcher_factory=FixtureMatcher)
        b=compare_observation_model(shifted,objects(),.18,matcher_factory=FixtureMatcher)
        self.assertEqual(a['status'],b['status'])
        self.assertNotEqual(a['best_diagnostic_hypothesis']['transform'],b['best_diagnostic_hypothesis']['transform'])
        self.assertAlmostEqual(a['best_diagnostic_hypothesis']['weighted_capped_mean_error_m'],b['best_diagnostic_hypothesis']['weighted_capped_mean_error_m'])
        self.assertFalse(b['alignment_verified'])

    def test_one_fixed_transform_cannot_claim_two_individually_good_poses(self):
        saved=observation();scene=objects();before=copy.deepcopy((saved,scene))
        result=compare_observation_model(saved,scene,.18,matcher_factory=FixtureMatcher)
        self.assertEqual(result['status'],'MODEL_OR_ODOM_INCONSISTENT')
        self.assertEqual(result['best_diagnostic_hypothesis']['supported_frames'],1)
        self.assertEqual(result['evaluated_keyframes'],2)
        self.assertEqual((saved,scene),before)
        self.assertFalse(result['geometry_changed']);self.assertFalse(result['motion_authorized'])
        self.assertFalse(result['alignment_verified']);self.assertFalse(result['physical_demo_ready'])

    def test_sensor_plane_excludes_tabletop_but_does_not_invent_legs(self):
        result=compare_observation_model(observation(),objects(),.18,matcher_factory=FixtureMatcher)
        rows={s['object_id']:s for s in result['sensor_sections']}
        self.assertFalse(rows['table']['intersects_nominal_scan_plane'])
        self.assertTrue(rows['chair']['intersects_nominal_scan_plane'])
        self.assertEqual(rows['chair']['review_priority'],'FURNITURE_LOWER_SECTION_UNKNOWN')
        self.assertEqual(result['surface_attribution_basis'],'NEAREST_AUTHORED_SURFACE_NOT_OBJECT_IDENTITY')
        self.assertEqual(len(result['outline']['segments']),8)

    def test_sparse_and_no_search_hypothesis_keep_explicit_gaps(self):
        value=observation();value['keyframes'][0]['points']=[]
        class NoPose(FixtureMatcher):
            def match(self,points):return {'status':'INSUFFICIENT_ANGULAR_COVERAGE','pose':None}
        report=compare_observation_model(value,objects(),.18,matcher_factory=NoPose)
        self.assertEqual(report['status'],'NO_SEARCH_HYPOTHESIS')
        self.assertEqual(report['skipped_sparse_keyframes'],1)
        self.assertIsNone(report['best_diagnostic_hypothesis']);self.assertEqual(report['overlays'],[])

    def test_invalid_frame_height_count_and_nan_rejected(self):
        for edit,reason in ((lambda v:v.update(coordinate_frame='room'),'FRAME_REQUIRED'),
                            (lambda v:v.update(keyframes=[]),'BUDGET'),
                            (lambda v:v['keyframes'][0]['points'].append([math.nan,0]),'VALUE')):
            value=observation();edit(value)
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                compare_observation_model(value,objects(),.18,matcher_factory=FixtureMatcher)
        for height in (False,0,math.nan):
            with self.subTest(height=height),self.assertRaisesRegex(ValueError,'HEIGHT_INVALID'):
                compare_observation_model(observation(),objects(),height,matcher_factory=FixtureMatcher)
