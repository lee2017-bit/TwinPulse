# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for source in ("packages/twinpulse_core/src", "packages/twinpulse_app/src", "packages/twinpulse_provider/src", "packages/twinpulse_core/tests", "scripts"):
    sys.path.insert(0, str(ROOT / source))
from test_native_scan import fixture
from test_native_registration import registration_fixture
from twinpulse_app.native_scan_review import NativeScanReview


class NativeScanReviewTests(unittest.TestCase):
    def test_registration_proposal_binding_and_import_reset(self):
        bundle, reference = registration_fixture()
        review = NativeScanReview()
        state = review.import_bundle(json.dumps(bundle.to_dict()))
        fitted = review.propose_registration(state['workspace_revision'], 0, json.dumps(reference))
        self.assertEqual(fitted['registration']['fit_status'], 'UNIQUE_CANDIDATE')
        self.assertFalse(fitted['registration']['world_alignment_verified'])
        self.assertNotEqual(fitted['workspace_revision'], state['workspace_revision'])
        with self.assertRaises(ValueError):
            review.propose_registration(state['workspace_revision'], 0, json.dumps(reference))
        exported = review.export_3d(0, fitted['workspace_revision'])
        self.assertEqual(exported['coordinate_frame'], 'sensor_native_unverified_axes')
        for text in ('{"x":1,"x":2}', '{"x":NaN}', ' '*65537, json.dumps(dict(reference, frame_index=1))):
            with self.assertRaises(ValueError): review.propose_registration(fitted['workspace_revision'], 0, text)
        self.assertEqual(review.snapshot(), fitted)
        self.assertIsNone(review.import_bundle(json.dumps(bundle.to_dict()))['registration'])

    def test_empty_import_preview_export_restart_and_no_authority(self):
        review = NativeScanReview()
        self.assertIsNone(review.snapshot()["bundle"])
        with self.assertRaises(ValueError): review.export_bundle()
        state = review.import_bundle(json.dumps(fixture()))
        self.assertEqual(state["bundle"]["frame_count"], 1)
        self.assertEqual(state["frame"]["invalid_returns"], 2)
        self.assertEqual(review.export_bundle(), fixture())
        for key in ("active_project_changed", "motion_authorized", "demo_ready", "source_bytes_verified", "handedness_verified"):
            self.assertIs(state[key], False)
        self.assertIsNone(state["world_tf"])
        self.assertEqual(state["analysis"]["clearance"], "UNKNOWN")
        state["analysis"]["angle_groups"].clear()
        self.assertEqual(len(review.snapshot()["analysis"]["angle_groups"]), 72)
        self.assertIsNone(NativeScanReview().snapshot()["bundle"])

    def test_reject_stale_bad_import_without_mutation_and_export_copy(self):
        review = NativeScanReview()
        state = review.import_bundle(json.dumps(fixture()))
        with self.assertRaises(ValueError): review.snapshot(0, "old")
        with self.assertRaises(ValueError): review.import_bundle('{"world_tf": {}}')
        self.assertEqual(review.snapshot(), state)
        value = review.export_bundle(); value["frames"].clear()
        self.assertEqual(review.snapshot(), state)
        review.import_bundle(json.dumps(fixture()))
        with self.assertRaises(ValueError): review.snapshot(0, state["workspace_revision"])

    def test_3d_export_requires_current_revision_preserves_workspace(self):
        review = NativeScanReview()
        with self.assertRaises(ValueError): review.export_3d(0, review.snapshot()['workspace_revision'])
        state = review.import_bundle(json.dumps(fixture()))
        result = review.export_3d(0, state['workspace_revision'])
        self.assertEqual(result['bundle_digest'], state['bundle']['digest'])
        self.assertFalse(result['motion_authorized'])
        self.assertEqual(review.snapshot(), state)
        for rev, index in [('stale', 0), (None, 0), (state['workspace_revision'], True), (state['workspace_revision'], 99)]:
            with self.subTest(rev=rev, index=index), self.assertRaises(ValueError): review.export_3d(index, rev)
        review.import_bundle(json.dumps(fixture()))
        with self.assertRaises(ValueError): review.export_3d(0, state['workspace_revision'])

    @unittest.skipUnless((ROOT / "artifacts/photo-scan-review-20260927/review.json").is_file(), "local actual recording is not shipped as a test fixture")
    def test_actual_saved_export_preserves_every_complete_sample(self):
        from export_native_scan_bundle import build_bundle
        scan = ROOT / "artifacts/lidar-capture-20260927-1214"
        bundle = build_bundle(scan, ROOT / "artifacts/photo-scan-review-20260927")
        value = bundle.to_dict()
        nodes = [json.loads(line) for line in (scan / "nodes.ndjson").read_text().splitlines()]
        self.assertEqual(len(value["frames"]), 74)
        count = 0
        for frame in value["frames"]:
            for beam in frame["beams"]:
                original = nodes[beam["node_index"]]
                for key in ("angle_deg", "distance_m", "quality", "source_byte_cursor"):
                    self.assertEqual(beam[key], original[key])
                count += 1
        self.assertGreater(count, 29000)
        last = bundle.frame_preview(73)
        self.assertEqual((last["samples"], len(last["points"]), last["invalid_returns"]), (403, 389, 14))
        self.assertEqual(value["photos"][1]["window_direction"], "up")
        self.assertNotIn("world_tf", value)


if __name__ == "__main__": unittest.main()
