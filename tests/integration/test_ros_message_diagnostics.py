# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline decoded-message diagnostics; never pose or motion qualification."""
from pathlib import Path
import sys
from types import SimpleNamespace as N
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from ros_message_diagnostics import review_replayed


def header(frame='odom', sec=1):
    return N(frame_id=frame, stamp=N(sec=sec, nanosec=0))


def quaternion(w=1):
    return N(x=0., y=0., z=0., w=w)


class MessageDiagnosticsTests(unittest.TestCase):
    def test_odom_shape_reason_is_bound_to_raw_sequence_without_pose_authority(self):
        valid=N(header=header(), child_frame_id='base_footprint',
                pose=N(pose=N(position=N(x=0., y=0., z=0.), orientation=quaternion())))
        invalid=N(header=header(), child_frame_id='base_footprint',
                  pose=N(pose=N(position=N(x=0., y=0., z=0.), orientation=quaternion(0))))
        result=review_replayed([({'sequence':3,'topic':'odom'},valid),
                                ({'sequence':4,'topic':'odom'},invalid)])
        self.assertEqual(result['status'],'ISSUES')
        self.assertEqual(result['findings']['odom']['SHAPE_OK_NOT_POSE_VERIFIED'],1)
        self.assertEqual(result['examples'],[{'sequence':4,'topic':'odom','reason':'ODOM_ORIENTATION'}])
        self.assertIn('NO_POSE_OR_MOTION_AUTHORITY',result['scope'])

    def test_scan_nonfinite_is_diagnosed_without_rewriting_ranges(self):
        rays=[1.0]*360
        rays[17]=float('inf')
        scan=N(header=header('laser'), ranges=rays, angle_min=0.,
               angle_max=359*2*3.141592653589793/360,
               angle_increment=2*3.141592653589793/360,
               range_min=.1, range_max=3., time_increment=0.)
        result=review_replayed([({'sequence':1,'topic':'scan'},scan)])
        self.assertEqual(result['examples'][0]['reason'],'SCAN_RANGES_UNUSABLE')
        self.assertEqual(rays[17],float('inf'))

    def test_tf_and_other_topics_are_explicitly_limited(self):
        transform=N(header=header('odom'), child_frame_id='base_footprint',
                    transform=N(translation=N(x=0.,y=0.,z=0.),rotation=quaternion()))
        result=review_replayed([({'sequence':0,'topic':'/tf'},N(transforms=[transform])),
                                ({'sequence':1,'topic':'sensor_state'},object()),
                                ({'sequence':2,'topic':'/tf_static'},N(transforms=[]))])
        self.assertEqual(result['findings']['/tf']['SHAPE_OK_NOT_TF_ALIGNED'],1)
        self.assertEqual(result['findings']['sensor_state']['NOT_SEMANTICALLY_REVIEWED'],1)
        self.assertEqual(result['examples'],[{'sequence':2,'topic':'/tf_static','reason':'TF_EMPTY'}])
        transform.header.stamp.sec=0
        static=review_replayed([({'sequence':3,'topic':'/tf_static'},N(transforms=[transform]))])
        self.assertEqual(static['findings']['/tf_static']['SHAPE_OK_NOT_TF_ALIGNED'],1)


if __name__ == '__main__':
    unittest.main()
