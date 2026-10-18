# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from twinpulse_core import WorldObservationRef
from twinpulse_core.native_scan import NativeScanBundle
from test_native_scan import fixture


class WorldObservationRefTests(unittest.TestCase):
    def test_photo_ref_is_source_bound_but_not_world_aligned(self):
        ref = WorldObservationRef.for_model_photo("a" * 64, "b" * 64, ("bed", "wall_1"))
        self.assertEqual(WorldObservationRef.from_dict(ref.to_dict()), ref)
        self.assertEqual(ref.coordinate_frame, "image_unregistered")
        self.assertEqual(ref.metric_status, "photo_estimate_only")
        self.assertFalse(ref.alignment_verified)
        self.assertFalse(ref.motion_authorized)
        ref.require_visual_ids(["bed"])
        with self.assertRaisesRegex(ValueError, "unobserved"):
            ref.require_visual_ids(["invented"])

    def test_saved_scan_ref_does_not_claim_raw_bytes_or_beam_time(self):
        bundle = NativeScanBundle.from_dict(fixture())
        ref = WorldObservationRef.for_native_scan(bundle)
        self.assertEqual(ref.artifact_sha256, bundle.digest)
        self.assertEqual(ref.source_sha256, fixture()["source"]["raw_sha256"])
        self.assertEqual(ref.time_basis, "host_window_not_beam_time")
        self.assertEqual(ref.metric_status, "sensor_ranges_unregistered")
        self.assertEqual(ref.evidence_ids, ())
        self.assertEqual(WorldObservationRef.from_dict(ref.to_dict()).digest, ref.digest)
        with self.assertRaises(ValueError):
            ref.require_visual_ids([])

    def test_rejects_authority_and_kind_claims(self):
        baseline = WorldObservationRef.for_model_photo("a" * 64, "b" * 64, ("bed",)).to_dict()
        for key, bad in (("alignment_verified", True), ("motion_authorized", True),
                         ("coordinate_frame", "map"), ("time_basis", "beam_time"),
                         ("metric_status", "measured"), ("source_sha256", "bad"),
                         ("kind", "live_scan"), ("evidence_ids", ["bed", "bed"])):
            value = copy.deepcopy(baseline)
            value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                WorldObservationRef.from_dict(value)
        value = copy.deepcopy(baseline)
        value["world_tf"] = {}
        with self.assertRaises(ValueError):
            WorldObservationRef.from_dict(value)
        with self.assertRaises(ValueError):
            WorldObservationRef(kind="model_photo", artifact_sha256="a" * 64,
                                source_sha256="b" * 64, evidence_ids=(), coordinate_frame="map",
                                time_basis="none", metric_status="photo_estimate_only",
                                alignment_verified=True)
