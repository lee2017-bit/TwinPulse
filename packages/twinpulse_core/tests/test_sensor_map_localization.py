# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from twinpulse_core.room_localization import PoseTimeline
from twinpulse_core.sensor_map_localization import EndpointMatcher, locate_in_sensor_map
from packages.twinpulse_core.tests.test_room_localization import fixture, pose, scan_points


def evidence(stamps, poses, *, source='reference', boot='ref-boot'):
    scans=[];odom=[]
    for i,(stamp,position) in enumerate(zip(stamps,poses)):
        points=scan_points(fixture(),position)
        scans.append({'stamp_ns':round(stamp*1e9),'time_increment':0.,'angle_min':0.,
                      'angle_increment':math.tau/120,'ranges_m':[math.hypot(*p) for p in points],
                      'frame_id':'base_scan','raw_sequence':100+i})
        odom.append(pose(round(stamp*1e9),*position))
    return {'scans':scans,'odom':odom,'timeline':PoseTimeline(odom),'source_revision':source,'boot_id':boot}


class FixtureMatcher:
    def __init__(self,reference): self.reference=reference
    def match(self,points):return {'status':'GEOMETRIC_CANDIDATE','pose':[0.,0.,0.],
                                 'alternatives':[{'pose':[0.,0.,0.]},{'pose':[1.,0.,0.]}]}
    def score(self,points,p):return (.01,1.) if p[0]<.5 else (.25,0.)
    def possible(self,p):return True


class SensorMapTests(unittest.TestCase):
    def test_changed_start_and_heading_are_found_without_query_global_odom_prior(self):
        reference=evidence([1,2,3],[[0,0,0],[-.6,.3,-.2],[.4,-.8,.3]])
        for true_pose,status in (([.3,-.3,2.3],'SENSOR_MAP_GEOMETRIC_CANDIDATE'),
                                 ([-.6,.5,-1.2],'AMBIGUOUS')):
            query=evidence([4,4.1,4.2],[true_pose]*3,source='independent',boot='query-boot')
            # A freshly reset odom origin carries no global location hint.
            query['odom']=[pose(s['stamp_ns']) for s in query['scans']];query['timeline']=PoseTimeline(query['odom'])
            before=copy.deepcopy((reference['scans'],query['scans']))
            result=locate_in_sensor_map(reference,query,1,[0,0,0],[0,0,0])
            with self.subTest(pose=true_pose):
                # An accurate best pose is insufficient when a rival remains.
                # Preserve rejection; do not weaken the uniqueness threshold.
                self.assertEqual(result['status'],status,result['best_diagnostic_hypothesis'])
                recovered=result['best_diagnostic_hypothesis']['sensor_pose_reference_candidate']
                self.assertLess(math.dist(recovered[:2],true_pose[:2]),.12)
                self.assertLess(abs(math.atan2(math.sin(recovered[2]-true_pose[2]),math.cos(recovered[2]-true_pose[2]))),.08)
                self.assertFalse(result['photo_geometry_used']);self.assertFalse(result['alignment_verified'])
                self.assertFalse(result['free_space_inferred']);self.assertFalse(result['motion_authorized'])
                self.assertEqual((reference['scans'],query['scans']),before)

    def test_shared_raw_or_boot_excludes_query_interval_and_preserves_original_indices(self):
        reference=evidence([.1,.2,.3,4,4.1,4.2,8,8.1,8.2],[[0,0,0]]*9)
        for same_raw,same_boot in ((True,False),(False,True)):
            query=evidence([4,4.1,4.2],[[0,0,0]]*3,source='reference' if same_raw else 'other',boot='ref-boot' if same_boot else 'other-boot')
            result=locate_in_sensor_map(reference,query,1,[0,0,0],[0,0,0],matcher_factory=FixtureMatcher)
            self.assertEqual(result['holdout']['excluded_reference_frames'],[3,4,5])
            self.assertEqual(result['reference_retained_scan_count'],6)
            self.assertFalse(result['holdout']['direct_query_scan_reuse'])
            self.assertTrue(all(p[3] not in [3,4,5] and p[4] not in [3,4,5] for p in result['reference_endpoint_cells']))
            self.assertEqual(result['query_frames'],[0,1,2])
            self.assertEqual([q['raw_sequence'] for q in result['query_provenance']],[100,101,102])

    def test_self_short_recording_does_not_pass_by_matching_itself(self):
        data=evidence([1,1.1,1.2],[[0,0,0]]*3)
        with self.assertRaisesRegex(ValueError,'REFERENCE_TOO_SMALL_AFTER_QUERY_HOLDOUT'):
            locate_in_sensor_map(data,data,1,[0,0,0],[0,0,0],matcher_factory=FixtureMatcher)

    def test_ambiguous_and_inconsistent_neighbours_do_not_create_alignment(self):
        reference=evidence([1,2,3],[[0,0,0]]*3)
        query=evidence([5,5.1,5.2],[[0,0,0],[0,0,0],[1,0,0]],source='other',boot='other')
        result=locate_in_sensor_map(reference,query,1,[0,0,0],[0,0,0],matcher_factory=FixtureMatcher)
        self.assertEqual(result['status'],'POOR_FIT');self.assertEqual(result['best_diagnostic_hypothesis']['supported_query_frames'],2)
        class Ambiguous(FixtureMatcher):
            def score(self,points,p):return .01,1.
        result=locate_in_sensor_map(reference,query,1,[0,0,0],[0,0,0],matcher_factory=Ambiguous)
        self.assertEqual(result['status'],'AMBIGUOUS');self.assertFalse(result['alignment_verified'])

    def test_invalid_frame_sparse_unknown_gap_and_endpoint_budget_are_explicit(self):
        reference=evidence([1,2,3],[[0,0,0]]*3)
        query=evidence([5,5.1,5.2],[[0,0,0]]*3,source='other',boot='other')
        for index in (True,-1,3):
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'QUERY_SCAN_FRAME_NOT_RECORDED'):
                locate_in_sensor_map(reference,query,index,[0,0,0],[0,0,0])
        sparse=copy.deepcopy(query);sparse['scans'][1]['ranges_m']=[None]*120
        with self.assertRaisesRegex(ValueError,'QUERY_SCAN_MATCH_POINT_BUDGET'):
            locate_in_sensor_map(reference,sparse,1,[0,0,0],[0,0,0])
        gap=evidence([5,5.1,6.2],[[0,0,0]]*3,source='other',boot='other')
        with self.assertRaisesRegex(ValueError,'QUERY_MULTIFRAME_TIME_GAP'):
            locate_in_sensor_map(reference,gap,1,[0,0,0],[0,0,0])
        for value,reason in (({'endpoint_cells':[],'bounds_m':[-1,1,-1,1]},'ENDPOINT_BUDGET'),
                             ({'endpoint_cells':[[0,0]]*24,'bounds_m':[-30,30,-30,30]},'FIELD_BUDGET')):
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):EndpointMatcher(value)
