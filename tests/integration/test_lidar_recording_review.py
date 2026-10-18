# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('lidar_review', Path(__file__).parents[2] / 'scripts/review_lidar_recording.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def packet(count=3):
    payload = b'\x28\xa0\x0f' * count
    checksum = 0x55aa ^ (count << 8 | 1) ^ 0x501 ^ 0xa01
    for _ in range(count):
        checksum ^= 0x28 ^ 0xfa0
    return b'\xaa\x55' + struct.pack('<BBHHH', 1, count, 0x501, 0xa01, checksum) + payload


class RecordingReviewTest(unittest.TestCase):
    def test_checksum_count_prefix_tail(self):
        data = b'COIN-D4' + packet() + packet()[:6]
        r = m.packets(data)
        self.assertEqual(r['good_packets'], 1)
        self.assertEqual(r['samples'], 3)
        self.assertEqual(r['skipped_bytes'], 7)
        self.assertEqual(r['trailing_bytes'], 6)
    def test_reject_bad_checksum_and_count(self):
        data = bytearray(packet())
        data[-1] ^= 1
        self.assertEqual(m.packets(data)['bad_checksum'], 1)
        data[3] = 86
        self.assertEqual(m.packets(data)['invalid_header'], 1)
    def test_every_truncation(self):
        data = packet()
        for i in range(len(data)):
            self.assertEqual(m.packets(data[:i])['good_packets'], 0)
    def test_no_invented_alignment_or_clearance(self):
        raw = packet(4)
        nodes = [dict(angle_deg=a, distance_m=d, quality=100, ring_start=r)
                 for a, d, r in [(0, 1, True), (90, 0, False), (180, 2, False), (0, 1, True)]]
        report = {'raw_sha256': hashlib.sha256(raw).hexdigest(), 'physical_rotor_stopped': 'UNCONFIRMED'}
        result, points = m.summarize(raw, nodes, report)
        self.assertEqual(result['complete_scans'], 1)
        self.assertEqual(len(points), 2)
        self.assertFalse(result['navigation_authorized'])
        self.assertEqual(result['obstacle_clearance'], 'UNKNOWN')
        self.assertEqual(result['world_tf'], 'UNVERIFIED')
        report['raw_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            m.summarize(raw, nodes, report)


if __name__ == '__main__':
    unittest.main()
