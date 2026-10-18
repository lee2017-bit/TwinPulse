# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import hashlib
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_3d import export_native_frame_3d
from test_native_scan import fixture


class Native3DTests(unittest.TestCase):
    def test_deterministic_preserved_samples_and_no_authority(self):
        bundle = NativeScanBundle.from_dict(fixture())
        result = export_native_frame_3d(bundle, 0)
        self.assertEqual(result, export_native_frame_3d(bundle, 0))
        self.assertEqual(result['sha256'], hashlib.sha256(result['usda'].encode()).hexdigest())
        self.assertEqual(result['bundle_digest'], bundle.digest)
        self.assertEqual(result['point_count'], len(bundle.frame_preview(0)['points']))
        self.assertEqual(result['excluded_count'], 2)
        self.assertFalse(result['motion_authorized'])
        self.assertIsNone(result['world_tf'])
        for forbidden in ('Physics', 'RigidBody', 'Collision', 'references =', 'payload =', 'timeSamples', 'Mesh', 'Robot', 'Task'):
            self.assertNotIn(forbidden, result['usda'])
        for field in ('nativeAngleDegrees', 'nativeRangeMeters', 'nativeQuality', 'sourceByteCursor', 'excludedNodeIndices'):
            self.assertIn(field, result['usda'])

    def test_invalid_frame_and_revalidation(self):
        bundle = NativeScanBundle.from_dict(fixture())
        for index in (True, -1, 1, 0.0, '0', None):
            with self.subTest(index=index), self.assertRaises(ValueError):
                export_native_frame_3d(bundle, index)
        with self.assertRaises(ValueError):
            export_native_frame_3d(NativeScanBundle('{"bad":1}'), 0)

    def test_display_hypothesis_is_not_applied(self):
        data = fixture()
        bundle = NativeScanBundle.from_dict(data)
        result = export_native_frame_3d(bundle, 0)
        self.assertNotIn('xformOp', result['usda'])
        self.assertNotIn('mirror_native_y', result['usda'])
        self.assertEqual(result['coordinate_frame'], 'sensor_native_unverified_axes')

    def test_all_invalid_returns_are_empty_not_invented(self):
        data = fixture()
        for beam in data['frames'][0]['beams']:
            beam['distance_m'] = 0
        result = export_native_frame_3d(NativeScanBundle.from_dict(data), 0)
        self.assertEqual(result['point_count'], 0)
        self.assertIn('point3f[] points = []', result['usda'])
        self.assertEqual(result['excluded_count'], len(data['frames'][0]['beams']))

if __name__ == '__main__': unittest.main()
