# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from twinpulse_core.navigation_binding import PlanarBinding, navigation_inputs
from twinpulse_core.local_navigation import checked_command
from twinpulse_core.ros_observations import RosObservations
from test_ros_observations import message


def artificial_binding(**changes):
    return replace(PlanarBinding('base_footprint','base_scan',(0.,0.,0.),
                                (.1,0.,0.),.18,'a'*64),**changes)


def sample():
    observations=RosObservations()
    for kind in ('odom','scan'):observations.receive(kind,message(kind),10**10,20.,1)
    return observations.snapshot(20.)


class NavigationBindingTests(unittest.TestCase):
    def test_source_unchanged_scalar_offset_not_fake_transformed_rays(self):
        value=sample();before=copy.deepcopy(value)
        pose,envelope=navigation_inputs(value,artificial_binding(),20.)
        self.assertEqual(pose.xy_yaw,(.1,.2,0.))
        self.assertAlmostEqual(envelope.clear_radius_m,math.cos(math.pi/72)-.1)
        self.assertEqual(envelope.oldest_sample_s,19.95)
        self.assertFalse(hasattr(envelope,'ranges_m'))
        self.assertEqual(value,before);self.assertFalse(value['alignment_verified'])
        self.assertTrue(checked_command(.03,0.,0.,envelope,20.,provenance='live_sensor')['allowed'])

    def test_planar_child_transform_rotates_translation_before_yaw(self):
        value=sample();value['odom']['quaternion_xyzw']=[0.,0.,math.sqrt(.5),math.sqrt(.5)]
        pose,_=navigation_inputs(value,artificial_binding(child_to_base=(.2,0.,.3)),20.)
        self.assertAlmostEqual(pose.xy_yaw[0],.1);self.assertAlmostEqual(pose.xy_yaw[1],.4)
        self.assertAlmostEqual(pose.xy_yaw[2],math.pi/2+.3)

    def test_no_default_binding_or_unreviewed_shape(self):
        for b in (None,{},artificial_binding(evidence_sha256='photo'),
                  artificial_binding(footprint_radius_m=.1),artificial_binding(base_to_scan=(0,0,float('nan'))),
                  artificial_binding(child_to_base=(True,0,0))):
            with self.assertRaisesRegex(ValueError,'NAVIGATION_BINDING_REQUIRED'):
                navigation_inputs(sample(),b,20.)

    def test_no_guess_of_frames_or_nonplanar_orientation(self):
        for key,value in (('frame_id','map'),('child_frame_id','base_link')):
            s=sample();s['odom'][key]=value
            with self.assertRaisesRegex(ValueError,'FRAME_MISMATCH'):
                navigation_inputs(s,artificial_binding(),20.)
        s=sample();s['scan']['frame_id']='laser'
        with self.assertRaisesRegex(ValueError,'FRAME_MISMATCH'):navigation_inputs(s,artificial_binding(),20.)
        s=sample();s['odom']['quaternion_xyzw']=[.1,0,0,math.sqrt(.99)]
        with self.assertRaisesRegex(ValueError,'NONPLANAR'):navigation_inputs(s,artificial_binding(),20.)

    def test_snapshot_age_source_age_and_skew(self):
        for now in (19.99,20.16,20.21,float('nan')):
            with self.assertRaises(ValueError):navigation_inputs(sample(),artificial_binding(),now)
        s=sample();s['odom']['sample_s']=19.89
        with self.assertRaisesRegex(ValueError,'TIME_SKEW'):navigation_inputs(s,artificial_binding(),20.)
        s=sample();s['scan']=None;s['faults']['scan']='STALE'
        with self.assertRaisesRegex(ValueError,'OBSERVATION_MISSING'):navigation_inputs(s,artificial_binding(),20.)

    def test_large_offset_clamps_to_blocked_not_negative_or_clear(self):
        s=sample();s['scan']['ranges_m']=[.3]*72
        _,envelope=navigation_inputs(s,artificial_binding(base_to_scan=(.4,0.,0.)),20.)
        self.assertEqual(envelope.clear_radius_m,0.)
        for v,w in ((.03,0),(-.03,0),(0,.2),(0,-.2)):
            self.assertFalse(checked_command(v,w,0,envelope,20.,provenance='live_sensor')['allowed'])

    def test_footprint_and_closing_gap_are_conservative(self):
        s=sample();s['scan']['ranges_m']=[.4]*72
        _,envelope=navigation_inputs(s,artificial_binding(footprint_radius_m=.4),20.)
        self.assertFalse(checked_command(.03,0,0,envelope,20.,provenance='live_sensor')['allowed'])
        s=sample();s['scan']['angle_increment_rad']=(math.tau-.005)/72
        _,envelope=navigation_inputs(s,artificial_binding(),20.)
        self.assertLess(envelope.clear_radius_m,math.cos(math.pi/72)-.1)


if __name__=='__main__':unittest.main()
