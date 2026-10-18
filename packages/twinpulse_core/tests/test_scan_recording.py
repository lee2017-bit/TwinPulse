# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from twinpulse_core.scan_recording import CONVENTION, MAX_BYTES, ScanRecording


def fixture():
    return {"schema_version": "scan-recording-1.0", "site_id": "test_room",
            "scene_revision": "a" * 64, "robot_profile_digest": "b" * 64,
            "session_id": "synthetic_session", "clock_id": "synthetic_clock",
            "provenance": "synthetic", "capture_mode": "stationary_snapshot", "convention": CONVENTION,
            "frames": [{"stamp_ns": 1_000_000_000, "frame_id": "laser", "clock_id": "synthetic_clock",
                        "angle_min_rad": 0, "angle_increment_rad": math.pi / 2,
                        "range_min_m": .1, "range_max_m": 10, "time_increment_ns": 0,
                        "ranges_m": [1, 2, None, 3],
                        "world_from_sensor": {"source_frame": "laser", "target_frame": "world",
                                              "stamp_ns": 1_000_000_000, "clock_id": "synthetic_clock",
                                              "x_m": 2, "y_m": 3, "yaw_rad": math.pi / 2}}]}


def replay(recording, **changes):
    args = {"site_id": "test_room", "scene_revision": "a" * 64, "robot_profile_digest": "b" * 64}
    args.update(changes)
    return recording.replay(**args)


class ScanRecordingTests(unittest.TestCase):
    def test_known_rotation_translation_and_missing_ray(self):
        result = replay(ScanRecording.from_dict(fixture()))
        self.assertEqual(result["valid_beams"], 3)
        self.assertEqual(result["invalid_beams"], 1)
        for point, expected in zip(result["points"], [(2, 4), (0, 3), (5, 3)]):
            self.assertAlmostEqual(point["x_m"], expected[0])
            self.assertAlmostEqual(point["y_m"], expected[1])
        self.assertEqual([p["beam_index"] for p in result["points"]], [0, 1, 3])

    def test_wrong_site_scene_and_profile_rejected(self):
        recording = ScanRecording.from_dict(fixture())
        for changes in ({"site_id": "another"}, {"scene_revision": "c" * 64}, {"robot_profile_digest": "c" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replay(recording, **changes)

    def test_tf_clock_frame_direction_and_age_rejected(self):
        for key, value in [("clock_id", "other"), ("source_frame", "base"), ("target_frame", "laser"),
                           ("stamp_ns", 1_050_000_001), ("stamp_ns", 949_999_999)]:
            data = fixture()
            data["frames"][0]["world_from_sensor"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                ScanRecording.from_dict(data)

    def test_tf_age_boundary_accepted(self):
        data = fixture()
        data["frames"][0]["world_from_sensor"]["stamp_ns"] += 50_000_000
        ScanRecording.from_dict(data)

    def test_no_rolling_scan_without_deskew(self):
        for value in [True, 1, -1, .0]:
            data = fixture()
            data["frames"][0]["time_increment_ns"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                ScanRecording.from_dict(data)

    def test_strict_range_values(self):
        for value in [float("nan"), float("inf"), True, "2", 0, -1, 10.01]:
            data = fixture()
            data["frames"][0]["ranges_m"][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                ScanRecording.from_dict(data)

    def test_empty_or_large_arrays_and_angular_span(self):
        for ranges in [[], [1] * 4097, [1] * 6]:
            data = fixture()
            data["frames"][0]["ranges_m"] = ranges
            with self.assertRaises(ValueError):
                ScanRecording.from_dict(data)
        for frames in [[], fixture()["frames"] * 33]:
            data = fixture()
            data["frames"] = frames
            with self.assertRaises(ValueError):
                ScanRecording.from_dict(data)

    def test_multiple_frames_monotonic_and_deterministic(self):
        data = fixture()
        next_frame = copy.deepcopy(data["frames"][0])
        next_frame["stamp_ns"] += 100_000_000
        next_frame["world_from_sensor"]["stamp_ns"] += 100_000_000
        data["frames"].append(next_frame)
        recording = ScanRecording.from_dict(data)
        self.assertEqual(replay(recording), replay(recording))
        self.assertEqual(replay(recording)["points"][-1]["frame_index"], 1)
        data["frames"].reverse()
        with self.assertRaises(ValueError):
            ScanRecording.from_dict(data)
        data = fixture()
        data["frames"] *= 2
        with self.assertRaises(ValueError):
            ScanRecording.from_dict(data)

    def test_all_missing_is_not_free_space(self):
        data = fixture()
        data["frames"][0]["ranges_m"] = [None] * 4
        result = replay(ScanRecording.from_dict(data))
        self.assertEqual(result["points"], [])
        self.assertEqual(result["invalid_beams"], 4)
        self.assertNotIn("occupancy", result)

    def test_point_budget(self):
        data = fixture()
        data["frames"][0]["ranges_m"] = [1] * 4096
        data["frames"][0]["angle_increment_rad"] = math.tau / 4096
        recording = ScanRecording.from_dict(data)
        for budget in [1, 7, 2048]:
            result = replay(recording, max_points=budget)
            self.assertLessEqual(len(result["points"]), budget)
            self.assertEqual(result["valid_beams"], 4096)
        for budget in [0, 2049, True, 1.0]:
            with self.assertRaises(ValueError):
                replay(recording, max_points=budget)

    def test_digest_roundtrip_and_input_not_aliased(self):
        data = fixture()
        recording = ScanRecording.from_json(json.dumps(data).encode())
        revision = recording.revision
        self.assertEqual(ScanRecording.from_dict(recording.to_dict()).revision, revision)
        data["frames"][0]["ranges_m"][0] = 8
        exported = recording.to_dict()
        exported["frames"][0]["ranges_m"][0] = 9
        self.assertEqual(recording.revision, revision)
        self.assertNotEqual(ScanRecording.from_dict(data).revision, revision)

    def test_strict_json_and_size(self):
        for payload in [b'{"frames":[],"frames":[]}', b'{"x":NaN}', b'\xff', b'[' * 2000,
                        b' ' * (MAX_BYTES + 1), b'[]']:
            with self.assertRaises(ValueError):
                ScanRecording.from_json(payload)
        data = fixture()
        data["command"] = "not permitted"
        with self.assertRaises(ValueError):
            ScanRecording.from_dict(data)

    def test_source_labels_never_grant_authority(self):
        for source in ["synthetic", "simulation", "recorded_sensor"]:
            data = fixture()
            data["provenance"] = source
            result = replay(ScanRecording.from_dict(data))
            self.assertEqual(result["provenance"], source)
            for key in ["source_verified", "alignment_verified", "motion_authorized", "demo_ready"]:
                self.assertIs(result[key], False)
            self.assertEqual(result["physical_validation"], "NOT_RUN")
        data["provenance"] = "live_verified"
        with self.assertRaises(ValueError):
            ScanRecording.from_dict(data)

    def test_unit_convention_and_capture_mode_rejected(self):
        for key, value in [("convention", "millimetres_degrees"), ("capture_mode", "moving"),
                           ("schema_version", "1"), ("clock_id", "other"), ("scene_revision", "bad")]:
            data = fixture()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ScanRecording.from_dict(data)

    def test_malformed_numeric_metadata_rejected(self):
        for key, value in [("stamp_ns", True), ("stamp_ns", 1.0), ("stamp_ns", -1),
                           ("angle_min_rad", float("inf")), ("range_max_m", .05),
                           ("angle_increment_rad", -1), ("angle_increment_rad", True)]:
            data = fixture()
            data["frames"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ScanRecording.from_dict(data)


if __name__ == "__main__":
    unittest.main()
