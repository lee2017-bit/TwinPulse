# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H3b synthetic corpus: no real-site photo or measured geometry is implied."""

from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from twinpulse_core.photo_track import PhotoTrackManifest, TrackMeasurement
from twinpulse_core.revisions import InputRevision


def _photo(content: bytes = b"synthetic-site-a") -> InputRevision:
    return InputRevision.create(prompt="test", images=[("site.png", "image/png", content)],
                                measurement_constraints=[], profile_id="generic_2wd",
                                generation_settings={"model_id": "fake"}, input_kind="photo")


def _bound(revision: InputRevision) -> PhotoTrackManifest:
    return PhotoTrackManifest(site_id="test_site_a", photo_input_digest=revision.digest,
                              photo_sha256=revision.images[0]["sha256"], photo_site_confirmed=True,
                              measurements=(TrackMeasurement("x", 4.0, 0.02, "tape"),
                                            TrackMeasurement("y", 3.0, 0.02, "tape")),
                              origin_marker="floor_corner_a", positive_x_marker="floor_corner_b")


class PhotoTrackTests(unittest.TestCase):
    def test_photo_review_does_not_require_manual_measurement(self):
        photo = _photo()
        manifest = PhotoTrackManifest(site_id="actual_site", photo_input_digest=photo.digest,
                                      photo_sha256=photo.images[0]["sha256"], photo_site_confirmed=True)
        manifest.verify_input(photo)
        self.assertTrue(manifest.ready_for_photo_review)
        self.assertFalse(manifest.ready_for_manual_alignment_review)

    def test_corpus_names_all_three_cases_without_claiming_final_photo(self):
        root = Path(__file__).resolve().parents[3]
        corpus = json.loads((root / "fixtures/h3b/corpus.json").read_text(encoding="utf-8"))
        self.assertEqual(corpus["schema_version"], "h3b-corpus-1.0")
        cases = {case["id"]: case for case in corpus["cases"]}
        self.assertEqual(set(cases), {"warehouse_regression", "nonwarehouse_contract", "final_physical_test_site"})
        self.assertTrue((root / cases["warehouse_regression"]["source"]).is_file())
        self.assertTrue((root / cases["nonwarehouse_contract"]["source"]).is_file())
        self.assertIsNone(cases["final_physical_test_site"]["source"])
        self.assertFalse(any(case["real_site_photo"] for case in cases.values()))

    def test_pending_actual_site_never_claims_ready(self):
        pending = PhotoTrackManifest(site_id="actual_demo_site")
        self.assertEqual(pending.relationship, "same_physical_site")
        self.assertEqual(pending.review_gaps, ("actual_site_photo", "same_site_confirmation",
                                               "measured_x_span", "measured_y_span",
                                               "origin_marker", "positive_x_marker"))
        self.assertFalse(pending.ready_for_alignment_review)
        self.assertEqual(PhotoTrackManifest.from_dict(pending.to_dict()), pending)

    def test_synthetic_same_site_binding_is_only_reviewable_not_drive_authorized(self):
        photo = _photo()
        manifest = _bound(photo)
        manifest.verify_input(photo)
        self.assertTrue(manifest.ready_for_alignment_review)
        self.assertEqual(PhotoTrackManifest.from_dict(manifest.to_dict()), manifest)

    def test_different_photo_or_text_cannot_reuse_manifest(self):
        manifest = _bound(_photo())
        with self.assertRaisesRegex(ValueError, "does not match"):
            manifest.verify_input(_photo(b"synthetic-site-b"))
        text = InputRevision.create(prompt="test", images=[], measurement_constraints=[],
                                    profile_id="generic_2wd", generation_settings={"model_id": "fake"},
                                    input_kind="text")
        with self.assertRaisesRegex(ValueError, "does not match"):
            manifest.verify_input(text)

    def test_unmeasured_and_unconfirmed_stay_pending(self):
        photo = _photo()
        manifest = PhotoTrackManifest(site_id="test_site_a", photo_input_digest=photo.digest,
                                      photo_sha256=photo.images[0]["sha256"],
                                      measurements=(TrackMeasurement("x", 4.0, 0.02, "tape"),))
        self.assertEqual(manifest.review_gaps, ("same_site_confirmation", "measured_y_span",
                                                "origin_marker", "positive_x_marker"))
        self.assertFalse(manifest.ready_for_alignment_review)

    def test_inferred_measurement_scaled_relation_and_duplicate_axes_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            TrackMeasurement("x", 4.0, 0.02, "photo_inference")
        with self.assertRaisesRegex(ValueError, "relationship"):
            PhotoTrackManifest(site_id="site_a", relationship="scaled_reproduction")
        with self.assertRaisesRegex(ValueError, "unique"):
            PhotoTrackManifest(site_id="site_a", measurements=(TrackMeasurement("x", 4, 0, "tape"),
                                                                  TrackMeasurement("x", 5, 0, "laser")))

    def test_tampered_hash_and_fake_confirmation_rejected(self):
        photo = _photo()
        manifest = _bound(photo)
        body = manifest.to_dict()
        body["origin_marker"] = "another_origin"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            PhotoTrackManifest.from_dict(body)
        with self.assertRaisesRegex(ValueError, "requires a bound photo"):
            PhotoTrackManifest(site_id="site_a", photo_site_confirmed=True)


if __name__ == "__main__":
    unittest.main()
