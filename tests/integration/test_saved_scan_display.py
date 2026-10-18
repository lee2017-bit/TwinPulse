# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline display audit of existing exact-byte COIN D4 samples, no transport.

This test-only decoder supports the saved CDR1 little-endian LaserScan shape.
It is not the production ROS replay decoder, TF verification or live acceptance.
"""
import hashlib
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from raw_ros_record import inspect_recording
from twinpulse_core.ros_observations import scan_preview,valid_scan_preview


def saved_laser_scan(payload):
    if payload[:4]!=b'\x00\x01\x00\x00':raise ValueError('CDR1_LE_REQUIRED')
    sec,nanosec,size=struct.unpack_from('<iII',payload,4)
    if not 1<=size<=80:raise ValueError('FRAME_LENGTH')
    frame=payload[16:16+size]
    if len(frame)!=size or frame[-1:]!=b'\0':raise ValueError('FRAME_TRUNCATED')
    pos=4+((16+size-4+3)//4)*4
    fields=struct.unpack_from('<7f',payload,pos);pos+=28
    count=struct.unpack_from('<I',payload,pos)[0];pos+=4
    if not 72<=count<=720:raise ValueError('RAY_LENGTH')
    rays=struct.unpack_from('<'+str(count)+'f',payload,pos);pos+=4*count
    intensities=struct.unpack_from('<I',payload,pos)[0];pos+=4
    if intensities>720 or pos+4*intensities!=len(payload):raise ValueError('CDR_TRAILING_OR_TRUNCATED')
    return NS(header=NS(frame_id=frame[:-1].decode('ascii'),stamp=NS(sec=sec,nanosec=nanosec)),
              angle_min=fields[0],angle_max=fields[1],angle_increment=fields[2],
              time_increment=fields[3],scan_time=fields[4],range_min=fields[5],range_max=fields[6],ranges=list(rays))


class SavedDisplayAudit(unittest.TestCase):
    def test_existing_105_real_scans_display_without_relabel_or_range_rescale(self):
        path=ROOT/'artifacts/ros-scan-20260930T143239Z-c4b681f5/ros-messages.raw'
        if not path.is_file():self.skipTest('Private saved raw fixture absent; live display NOT verified')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
            '33efb640cb759c7deeb63b089c786d38b35d7d8cdd9aa2f9680d24fd242d253b')
        samples=[(m,p) for m,p in inspect_recording(path) if m['topic']=='scan']
        self.assertEqual(len(samples),105)
        for metadata,payload in samples:
            with self.subTest(sequence=metadata['sequence']):
                msg=saved_laser_scan(payload);diagnostic={}
                stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
                preview=scan_preview(msg,stamp+50_000_000,20.,diagnostic=diagnostic)
                self.assertEqual(diagnostic['reason'],'NONE')
                self.assertTrue(valid_scan_preview(preview))
                self.assertEqual(preview['frame_id'],msg.header.frame_id)
                self.assertEqual(preview['angle_increment_rad'],msg.angle_increment)
                self.assertEqual(preview['range_max_m'],100.)
                self.assertFalse(preview['alignment_verified']);self.assertTrue(preview['display_only'])

