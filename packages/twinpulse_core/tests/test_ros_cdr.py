# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import math
import struct
import unittest
from twinpulse_core.ros_cdr import decode_mapping_message


class Writer:
    def __init__(self, order='<'):
        self.order=order;self.data=bytearray(b'\0\1\0\0' if order=='<' else b'\0\0\0\0')
    def put(self,fmt,alignment,*values):
        self.data.extend(b'\0'*((-(len(self.data)-4))%alignment));self.data.extend(struct.pack(self.order+fmt,*values))
    def string(self,value):
        data=value.encode()+b'\0';self.put('I',4,len(data));self.data.extend(data)
    def header(self):self.put('iI',4,100,123);self.string('base_scan')


def laser(order='<'):
    w=Writer(order);w.header()
    w.put('7f',4,0.,.2,.1,.001,.1,.1,100.)
    w.put('I3f',4,3,1.,float('inf'),float('nan'));w.put('I',4,0)
    return bytes(w.data)


class CdrTests(unittest.TestCase):
    def test_signed_angles_keep_range_and_time_order(self):
        w=Writer();w.header();w.put('7f',4,0.,-.2,-.1,.001,.1,.1,100.)
        w.put('I3f',4,3,1.,2.,3.);w.put('I',4,0)
        value=decode_mapping_message('sensor_msgs/msg/LaserScan',bytes(w.data))
        self.assertEqual(value['ranges_m'],[1.,2.,3.])
        self.assertLess(value['angle_increment'],0);self.assertGreater(value['time_increment'],0)

    def test_endian_nan_unknown_and_original_timing(self):
        for endian in ('<','>'):
            value=decode_mapping_message('sensor_msgs/msg/LaserScan',laser(endian))
            self.assertEqual(value['stamp_ns'],100_000_000_123)
            self.assertEqual(value['ranges_m'],[1.,None,None]);self.assertAlmostEqual(value['time_increment'],.001)

    def test_truncated_unknown_encoding_and_trailing_data_rejected(self):
        for value in (laser()[:-1],b'\0\7\0\0'+laser()[4:],laser()+b'garbage!'):
            with self.subTest(value=len(value)),self.assertRaises(ValueError):decode_mapping_message('sensor_msgs/msg/LaserScan',value)

    def test_sequence_budget_is_checked_before_allocation(self):
        w=Writer();w.put('I',4,129)
        with self.assertRaisesRegex(ValueError,'BUDGET'):decode_mapping_message('tf2_msgs/msg/TFMessage',bytes(w.data))

    def test_odometry_and_tf_alignment_and_covariances(self):
        w=Writer();w.header();w.string('base_link');w.put('3d',8,1,2,0);w.put('4d',8,0,0,0,1)
        w.put('36d',8,*([0]*36));w.put('6d',8,*([0]*6));w.put('36d',8,*([0]*36))
        odom=decode_mapping_message('nav_msgs/msg/Odometry',bytes(w.data));self.assertEqual(odom['position_m'],[1,2,0])
        w=Writer();w.put('I',4,1);w.header();w.string('base_link');w.put('3d',8,1,2,0);w.put('4d',8,0,0,0,1)
        tf=decode_mapping_message('tf2_msgs/msg/TFMessage',bytes(w.data))
        self.assertEqual(tf['transforms'][0]['translation_m'],odom['position_m'])


if __name__=='__main__':unittest.main()
