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
from twinpulse_core.native_scan import MAX_NATIVE_BYTES, NativeScanBundle


def fixture():
    return {"schema_version": "native-scan-bundle-1.0", "source": {
        "kind": "synthetic_test_fixture", "raw_sha256": "a" * 64, "nodes_sha256": "b" * 64,
        "observation_start_utc": "2026-09-27T03:13:54Z", "observation_end_utc": "2026-09-27T03:14:05Z",
        "timestamp_basis": "host_observation_window_not_beam_time"},
        "frames": [{"index": 0, "beams": [
            {"angle_deg": angle, "distance_m": distance, "quality": quality,
             "node_index": i + 7, "source_byte_cursor": 100 + i}
            for i, (angle, distance, quality) in enumerate([(0., 1., 100), (12.3, 2., 100), (90., 0., 0), (130., .1, 30)])]}],
        "photos": [{"role": "room", "sha256": "c" * 64, "media_type": "image/jpeg",
                    "same_position_user_declared": True, "window_direction": "unspecified"}],
        "display_hypotheses": [{"id": "mirror1", "rotation_deg": 213.015, "mirror_native_y": True}]}


class NativeScanTests(unittest.TestCase):
    def test_nonuniform_angles_zero_and_quality_preserved_without_interpolation(self):
        value = fixture()
        bundle = NativeScanBundle.from_text(json.dumps(value))
        self.assertEqual(bundle.to_dict(), value)
        frame = bundle.frame_preview(0)
        self.assertEqual((frame["samples"], frame["invalid_returns"]), (4, 2))
        self.assertEqual([p["node_index"] for p in frame["points"]], [7, 8])
        self.assertAlmostEqual(frame["points"][1]["y_m"], 2 * math.sin(math.radians(12.3)))

    def test_digest_canonical_and_data_isolated(self):
        value = fixture()
        a = NativeScanBundle.from_dict(value)
        b = NativeScanBundle.from_text(json.dumps(value, indent=3))
        self.assertEqual(a.digest, b.digest)
        value["frames"][0]["beams"][0]["distance_m"] = 42
        exported = a.to_dict()
        exported["photos"].clear()
        self.assertEqual(a.to_dict()["frames"][0]["beams"][0]["distance_m"], 1)
        self.assertEqual(len(a.to_dict()["photos"]), 1)

    def test_rejects_extra_authority_transform_or_source_path(self):
        for key, bad in [("world_tf", {}), ("motion_authorized", True), ("source_path", "C:/private"), ("robot_profile", {})]:
            value = fixture(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                NativeScanBundle.from_dict(value)

    def test_rejects_malformed_measurements_and_identity(self):
        for key, bad in [("angle_deg", True), ("angle_deg", float("nan")), ("angle_deg", -1),
                         ("angle_deg", 361), ("distance_m", float("inf")), ("distance_m", -1),
                         ("quality", 256), ("quality", False), ("node_index", 8), ("source_byte_cursor", -1),
                         ("distance_m", 10 ** 3000)]:
            value = fixture(); value["frames"][0]["beams"][0][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                NativeScanBundle.from_dict(value)

    def test_rejects_bad_provenance_and_time_claims(self):
        for key, bad in [("raw_sha256", "no"), ("kind", "live"), ("timestamp_basis", "beam_time"),
                         ("observation_end_utc", "2026-09-27T03:13:50Z"),
                         ("observation_end_utc", "2026-02-30T03:14:05Z"),
                         ("observation_start_utc", "2026-09-27T03:13:54+00:00")]:
            value = fixture(); value["source"][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                NativeScanBundle.from_dict(value)

    def test_bounded_collections_and_duplicate_bindings(self):
        mutations = [lambda v: v.update(frames=[]), lambda v: v.update(frames=v["frames"] * 101),
                     lambda v: v["frames"][0].update(beams=v["frames"][0]["beams"] * 1025),
                     lambda v: v["photos"].append(copy.deepcopy(v["photos"][0])),
                     lambda v: v["display_hypotheses"].append(copy.deepcopy(v["display_hypotheses"][0])),
                     lambda v: v["display_hypotheses"][0].update(rotation_deg=361),
                     lambda v: v["photos"][0].update(window_direction="robot_forward")]
        for mutation in mutations:
            value = fixture(); mutation(value)
            with self.assertRaises(ValueError): NativeScanBundle.from_dict(value)

    def test_json_duplicate_nonfinite_oversize_and_nesting_rejected(self):
        for text in ['{"schema_version":1,"schema_version":2}', 'NaN', "[" * 2000 + "]" * 2000,
                     " " * (MAX_NATIVE_BYTES + 1), None]:
            with self.assertRaises(ValueError): NativeScanBundle.from_text(text)

    def test_frame_selection_strict_no_negative_boolean_or_float(self):
        bundle = NativeScanBundle.from_dict(fixture())
        for bad in [-1, 1, True, 0., "0", None]:
            with self.assertRaises(ValueError): bundle.frame_preview(bad)


if __name__ == "__main__":
    unittest.main()
