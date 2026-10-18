# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from twinpulse_core.room_localization import PoseTimeline
from twinpulse_core.scan_observation import acquisition_timing_candidate, build_observation_map
from packages.twinpulse_core.tests.test_room_localization import pose


def scans():
    return [{'stamp_ns':1_000_000_000+i*50_000_000,'frame_id':'base_scan','raw_sequence':i,
             'angle_min':0.,'angle_increment':math.pi/2,'time_increment':.001,
             'ranges_m':[1.,None,1.,9.]} for i in range(3)]


class ObservationTests(unittest.TestCase):
    def test_clock_bridge_uses_acquisition_not_publication_time(self):
        result=acquisition_timing_candidate(10_000,12_000,1_000_000,[0,500,1000])
        self.assertEqual(result['first_ray_ros_ns_candidate'],998_000)
        self.assertEqual(result['time_increment_ns'],500)
        self.assertFalse(result['acquisition_timing_verified'])
        for offsets in ([0,-1,-2],[0,500,750],[100,600],[0,1000,3000]):
            with self.subTest(offsets=offsets),self.assertRaises(ValueError):
                acquisition_timing_candidate(10_000,12_000,1_000_000,offsets)

    def test_clock_reset_cross_domain_and_bad_samples_rejected(self):
        for args in ((20,10,100,[0,1]),(0,3_000_000_000,4_000_000_000,[0,1]),
                     (0,100,10,[0,1]),(False,10,100,[0,1]),(0,10,100,[0,1.]),
                     (2**64-5,2,100,[0,1]),(2**63,2**63+10,2**63+100,[0,1])):
            with self.subTest(args=args),self.assertRaises(ValueError):acquisition_timing_candidate(*args)

    def test_map_uses_all_paired_scans_and_keeps_unknowns_and_originals(self):
        rows=[pose(1_000_000_000+i*50_000_000,x=.05*i) for i in range(4)]
        original=scans();before=copy.deepcopy(original)
        result=build_observation_map(original,PoseTimeline(rows),[0,0,0])
        self.assertEqual(original,before);self.assertEqual(result['paired_frames'],3)
        self.assertEqual(result['sampled_hits'],6);self.assertEqual(len(result['keyframes']),3)
        self.assertEqual(result['beyond_display_range_returns'],3)
        for key in ('photo_geometry_used','free_space_inferred','pose_correction_applied',
                    'motion_authorized','physical_demo_ready'):
            self.assertIs(result[key],False)
        self.assertFalse(result['timing']['acquisition_timing_verified'])
        self.assertAlmostEqual(result['keyframes'][1]['sensor_pose'][0],.05)

    def test_session_origin_and_yaw_are_not_previous_room_pose(self):
        rows=[pose(1_000_000_000+i*50_000_000,x=10,y=5,yaw=math.pi/2) for i in range(4)]
        result=build_observation_map(scans(),PoseTimeline(rows),[0,0,0])
        self.assertAlmostEqual(result['keyframes'][0]['sensor_pose'][0],0)
        self.assertAlmostEqual(result['keyframes'][0]['points'][0][0],1)
        self.assertEqual(result['odom_anchor_pose'][:2],[10,5])

    def test_gap_rejection_does_not_hide_other_frames(self):
        rows=[pose(1_000_000_000),pose(1_050_000_000),pose(1_250_000_000),pose(1_300_000_000)]
        original=scans();original[-1]['stamp_ns']=1_250_000_000
        result=build_observation_map(original,PoseTimeline(rows),[0,0,0])
        self.assertEqual(result['paired_frames'],2);self.assertEqual(result['rejected_frames'],1)
        self.assertEqual(result['failures'][0]['reason'],'ODOM_TIME_GAP')
        self.assertEqual([f['frame'] for f in result['keyframes']],[0,2])

    def test_no_returns_frame_change_reset_extent_and_counts_fail_explicitly(self):
        rows=PoseTimeline([pose(1_000_000_000+i*50_000_000) for i in range(4)])
        cases=[]
        empty=scans();empty[0]['ranges_m']=[None]*4;cases.append((empty[:1],'NO_PAIRED_RETURNS'))
        changed=scans();changed[-1]['frame_id']='other';cases.append((changed,'FRAME_CHANGED'))
        reset=scans();reset[-1]['stamp_ns']=reset[0]['stamp_ns'];cases.append((reset,'CLOCK_RESET'))
        cases.append(([],'SCAN_BUDGET'))
        for source,reason in cases:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):build_observation_map(source,rows,[0,0,0])
        with self.assertRaisesRegex(ValueError,'EXTENT_BUDGET'):
            build_observation_map(scans(),PoseTimeline([pose(1_000_000_000),pose(1_050_000_000,x=30),pose(1_150_000_000,x=30)]),[0,0,0])


if __name__=='__main__':unittest.main()
