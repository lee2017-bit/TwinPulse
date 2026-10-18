# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import importlib.util
import math
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('photo_scan_review', Path(__file__).parents[2] / 'scripts/prepare_photo_scan_review.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PhotoScanReviewTest(unittest.TestCase):
    def test_confirmation_not_reused_for_another_photo_or_scan(self):
        m.require_confirmed_pair(m.CONFIRMED_PHOTO_SHA256, m.CONFIRMED_RAW_SHA256)
        for photo, scan in [('0'*64, m.CONFIRMED_RAW_SHA256), (m.CONFIRMED_PHOTO_SHA256, '0'*64)]:
            with self.assertRaises(ValueError):
                m.require_confirmed_pair(photo, scan)
    def test_bounded_input(self):
        for pts in ([], [{'x_m': 0, 'y_m': 0}], [{'x_m': 0, 'y_m': float('nan')}]*2,
                    [{'x_m': 0, 'y_m': 0}]*4097):
            with self.assertRaises(ValueError):
                m.fit_segments(pts)
    def test_deterministic_observed_segment(self):
        pts = [{'x_m': i*.04, 'y_m': .5} for i in range(30)]
        a = m.fit_segments(pts)
        self.assertEqual(a, m.fit_segments(pts))
        self.assertEqual(len(a), 1)
        self.assertAlmostEqual(a[0]['length_m'], 1.16)
        self.assertAlmostEqual(a[0]['rms_residual_m'], 0)
        self.assertEqual(a[0]['object_identity'], 'UNASSIGNED')
    def test_gap_does_not_invent_bridge(self):
        pts = [{'x_m': i*.03, 'y_m': .5} for i in range(20)]
        pts += [{'x_m': 3+i*.03, 'y_m': .5} for i in range(20)]
        lines = m.fit_segments(pts)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line['length_m'] < .6 for line in lines))
    def test_orientation_not_unique_and_distances_preserved(self):
        candidates = m.orientation_candidates([{'direction_deg_mod180':123}])
        self.assertEqual(len(candidates), 8)
        for c in candidates:
            x, y = m.transform_point(1, 2, c['rotation_deg'], c['mirror_native_y'])
            self.assertAlmostEqual(math.hypot(x, y), math.sqrt(5))
            self.assertEqual(c['status'], 'UNVERIFIED_DISPLAY_HYPOTHESIS')
        self.assertEqual(m.orientation_candidates([]), [])
    def test_photo_boxes_are_relative_not_metres(self):
        for obj in m.PHOTO_OBSERVATIONS:
            x0,y0,x1,y1 = obj['box_normalized']
            self.assertTrue(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1)
            self.assertNotIn('dimensions_m', obj)
    def test_html_is_local_and_does_not_execute_motion(self):
        html = m.report_html({'orientation_candidates':m.orientation_candidates([{'direction_deg_mod180':123}]), 'surface_segments':[]})
        self.assertNotIn('fetch(', html)
        self.assertNotIn('https://', html)
        self.assertIn('candidate-mirror1.png', html)
        self.assertIn('대안 방향 후보', html)


if __name__ == '__main__':
    unittest.main()
