# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_native_scan import fixture
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_quality import analyze_native_scan


class NativeScanQualityTests(unittest.TestCase):
    def test_missing_returns_unknown_and_no_single_frame_accuracy(self):
        bundle = NativeScanBundle.from_dict(fixture())
        before = bundle.to_dict()
        result = analyze_native_scan(bundle)
        self.assertEqual(result["sample_count"], 4)
        self.assertEqual(result["excluded_count"], 2)
        self.assertEqual(result["never_observed_angle_bins"], 70)
        self.assertAlmostEqual(result["worst_return_gap_deg"], 347.7)
        self.assertEqual(result["clearance"], "UNKNOWN")
        self.assertIsNone(result["angle_groups"][0]["median_absolute_deviation_m"])
        self.assertIsNone(result["angle_groups"][1]["median_of_frame_medians_m"])
        for key in ("stationarity_verified", "range_accuracy_verified", "world_tf_verified", "motion_authorized"):
            self.assertFalse(result[key])
        self.assertEqual(bundle.to_dict(), before)

    def test_cross_frame_statistics_use_each_frames_median_not_sample_density(self):
        value = fixture()
        second = copy.deepcopy(value["frames"][0]); second["index"] = 1
        for beam in second["beams"]:
            beam["node_index"] += 4; beam["source_byte_cursor"] += 4
        second["beams"][0]["distance_m"] = 3
        value["frames"].append(second)
        result = analyze_native_scan(NativeScanBundle.from_dict(value))
        first = result["angle_groups"][0]
        self.assertEqual(first["frames_with_returns"], 2)
        self.assertEqual(first["median_of_frame_medians_m"], 2)
        self.assertEqual(first["median_absolute_deviation_m"], 1)
        self.assertAlmostEqual(first["p10_frame_median_m"], 1.2)
        self.assertAlmostEqual(first["p90_frame_median_m"], 2.8)

    def test_all_invalid_no_fabricated_ranges(self):
        value = fixture()
        for beam in value["frames"][0]["beams"]: beam["distance_m"] = 0
        result = analyze_native_scan(NativeScanBundle.from_dict(value))
        self.assertEqual(result["excluded_percent"], 100)
        self.assertEqual(result["worst_return_gap_deg"], 360)
        self.assertEqual(result["never_observed_angle_bins"], 72)
        self.assertIsNone(result["frames"][0]["min_return_m"])
        self.assertTrue(all(g["p90_frame_median_m"] is None for g in result["angle_groups"]))

    def test_zero_360_wrap_preserves_original_angles(self):
        value = fixture()
        beams = value["frames"][0]["beams"]
        beams[0]["angle_deg"] = 360
        beams[1]["angle_deg"] = 359
        bundle = NativeScanBundle.from_dict(value)
        result = analyze_native_scan(bundle)
        self.assertEqual(result["angle_groups"][0]["frames_with_returns"], 1)
        self.assertEqual(result["angle_groups"][71]["frames_with_returns"], 1)
        self.assertEqual(bundle.to_dict()["frames"][0]["beams"][0]["angle_deg"], 360)


if __name__ == "__main__": unittest.main()
