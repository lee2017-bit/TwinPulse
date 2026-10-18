# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
from twinpulse_app.bedroom_twin import bedroom_draft, bedroom_manifest
from twinpulse_app.site_draft import SiteDraftRecord


class BedroomTwinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.photo = (ROOT / "artifacts/photo-scan-review-20260927/room.jpg").read_bytes()
        cls.draft = bedroom_draft(cls.photo)

    def test_saved_project_cannot_be_rebound_to_another_image(self):
        with self.assertRaisesRegex(ValueError, "Historical project source"):
            bedroom_draft(b"unrelated photo")

    def test_product_record_roundtrip_and_determinism(self):
        self.assertEqual(self.draft, bedroom_draft(self.photo))
        self.assertEqual(self.draft.to_dict(), SiteDraftRecord.from_dict(self.draft.to_dict()).to_dict())

    def test_visible_objects_bound_to_observations(self):
        scene = self.draft.site.scene
        self.assertEqual(len(scene.objects), 12)
        for name in ("bed", "wardrobe", "desk", "chair", "fan_boxes", "bag", "left_luggage"):
            self.assertTrue(any(binding.scene_object_id == name for binding in scene.observation_bindings))
        self.assertFalse(self.draft.input_revision.measurement_constraints)
        self.assertFalse(any(e.basis == "trusted_measurement" for e in self.draft.plan.call_evidence))

    def test_draft_has_no_driven_robot_mission_or_warehouse_profile(self):
        self.assertIsNone(self.draft.site.robot)
        self.assertIsNone(self.draft.site.mission)
        self.assertTrue(self.draft.site.review_required)
        self.assertEqual(self.draft.input_revision.profile_id, "burger-visual-preview-unqualified")

    def test_tampered_geometry_rejected(self):
        value = json.loads(json.dumps(self.draft.to_dict()))
        value["site"]["scene"]["objects"][0]["shape"]["dimensions_m"][0] = 10
        with self.assertRaises(ValueError):
            SiteDraftRecord.from_dict(value)

    def test_no_fabricated_transform_or_authority(self):
        manifest = bedroom_manifest(self.draft, {"robot.usda": "1" * 64})
        self.assertIsNone(manifest["sensor_to_world_transform"])
        self.assertFalse(manifest["alignment_verified"])
        self.assertFalse(manifest["execution_authority"])
        self.assertEqual(manifest["robot_placement"]["physics_variant"], "none")

    def test_manifest_binds_asset_bytes(self):
        a = bedroom_manifest(self.draft, {"robot.usda": "1" * 64})
        b = bedroom_manifest(self.draft, {"robot.usda": "2" * 64})
        self.assertNotEqual(a["manifest_sha256"], b["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
