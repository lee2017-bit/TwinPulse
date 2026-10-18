# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit synthetic geometry, no robot or active project mutation."""
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
from twinpulse_app import ApplicationService, SiteDraftRecord
from twinpulse_app.scan_review import ScanReview
from twinpulse_app.derived_site_review import DerivedSiteReview, DerivedReviewStore
from twinpulse_core import SceneToolCall, SiteToolPlan, demo_warehouse_tool_plan
from twinpulse_core.scan_recording import ScanFrame, ScanRecording, Transform2D


def derived_fixture():
    prepared = ApplicationService.prepare_input(prompt="Synthetic derived scene fixture", images=(),
        measurement_constraints=(), generation_settings={"model_id": "offline-fixture"})
    demo = demo_warehouse_tool_plan()
    plan = SiteToolPlan("derived_fixture", "Explicit synthetic room", "No device or provider",
        (demo.calls[0], SceneToolCall("wall", "create_wall", {"id": "wall", "position_m": [1., 1., .5],
         "dimensions_m": [1., .2, 1.], "yaw_deg": 0.}), demo.calls[-2]))
    source = SiteDraftRecord.create(request_id="derived-test", provider_name="synthetic",
        model_id="synthetic", image_count=0, input_revision=prepared.revision, plan=plan)
    points = ((1.6, 1.), (1.6, 1.2))  # same box's right corners, translated (+.1,+.1)
    angles = [math.atan2(y, x) for x, y in points]
    frame = ScanFrame(1_000_000_000, "laser", "test_clock", angles[0], angles[1]-angles[0],
        .05, 10., 0, tuple(math.hypot(x, y) for x, y in points),
        Transform2D("laser", "world", 1_000_000_000, "test_clock", 0., 0., 0.))
    recording = ScanRecording(source.site.scene.id, source.site.scene.revision, source.site.robot.profile_digest,
        "synthetic_derived_review", "test_clock", "synthetic", (frame,))
    review = ScanReview()
    state = review.import_bundle(json.dumps({"schema_version": "offline-scan-bundle-1.0",
        "site_plan": source.site.to_dict(), "recording": recording.to_dict()}))
    pairs = [{"frame_index": 0, "beam_index": i, "object_local_xy_m": [.5, y]} for i, y in enumerate([-.1, .1])]
    state = review.propose(state["workspace_revision"], "wall", pairs)
    state = review.apply(state["workspace_revision"], state["proposal"]["revision"])
    text = review.download_archive(state["workspace_revision"])["archive_text"]
    return source, text


class DerivedReviewTests(unittest.TestCase):
    def test_roundtrip_preserves_original_and_new_geometry_without_authority(self):
        source, text = derived_fixture()
        before = source.to_dict()
        record = DerivedSiteReview.create(source, text)
        checked = DerivedSiteReview.from_dict(json.loads(json.dumps(record.to_dict())))
        self.assertEqual(record, checked)
        self.assertEqual(source.to_dict(), before)
        self.assertEqual(record.source.to_dict(), before)
        wall = next(o for o in record.site.scene.objects if o.id == "wall")
        self.assertAlmostEqual(wall.transform.position_m[0], 1.1)
        self.assertAlmostEqual(wall.transform.position_m[1], 1.1)
        self.assertEqual(wall.transform.position_m[2], .5)
        self.assertEqual(record.site.scene.parent_revision, source.site.scene.revision)
        self.assertIsNone(record.site.navigation_map)
        self.assertIsNone(record.site.mission)
        for flag in ("build_authorized", "active_project_changed", "motion_authorized", "source_verified"):
            self.assertFalse(record.summary()[flag])

    def test_different_original_plan_and_tampered_geometry_rejected(self):
        source, text = derived_fixture()
        changed_plan = replace(source.plan, calls=(source.plan.calls[0], replace(source.plan.calls[1],
            arguments=dict(source.plan.calls[1].arguments, position_m=[2., 1., .5])), source.plan.calls[-1]))
        changed = SiteDraftRecord.create(request_id=source.request_id, provider_name=source.provider_name,
            model_id=source.model_id, image_count=0, input_revision=source.input_revision, plan=changed_plan)
        with self.assertRaisesRegex(ValueError, "archive base differs"):
            DerivedSiteReview.create(changed, text)
        record = DerivedSiteReview.create(source, text)
        for key, value in (("revision", "a"*64), ("execution_authority", True), ("source_verified", True), ("unknown", 0)):
            bad = record.to_dict(); bad[key] = value
            with self.assertRaises(ValueError): DerivedSiteReview.from_dict(bad)
        bad = json.loads(json.dumps(record.to_dict())); bad["derived_site"]["scene"]["objects"][1]["transform"]["position_m"][0] += .1
        with self.assertRaises(ValueError): DerivedSiteReview.from_dict(bad)

    def test_direct_forged_dataclass_cannot_be_saved(self):
        source, text = derived_fixture()
        record = DerivedSiteReview.create(source, text)
        with TemporaryDirectory() as folder:
            store = DerivedReviewStore(Path(folder)/"review.json")
            with self.assertRaises(ValueError): store.save(replace(record, revision="forged"))
            self.assertFalse(store.path.exists())

    def test_atomic_store_failure_preserves_previous_record_and_only_cleans_own_temp(self):
        source, text = derived_fixture()
        record = DerivedSiteReview.create(source, text)
        with TemporaryDirectory() as folder:
            root = Path(folder); store = DerivedReviewStore(root/"review.json")
            original_project = root/"active_project.json"; original_project.write_text("unrelated fixture")
            stale = root/"review.json.tmp-unrelated"; stale.write_text("leave alone")
            self.assertIsNone(store.load())
            store.save(record)
            self.assertEqual(store.load(), record)
            before = store.path.read_bytes()
            with patch.object(Path, "replace", side_effect=OSError("fixture replace failure")):
                with self.assertRaises(OSError): store.save(record)
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(original_project.read_text(), "unrelated fixture")
            self.assertTrue(stale.exists())
            self.assertEqual(len(list(root.glob("review.json.tmp-*"))), 1)

    def test_duplicate_nonfinite_oversized_and_empty_history_rejected(self):
        source, text = derived_fixture()
        review = ScanReview(); state = review.import_archive(review.snapshot()["workspace_revision"], text)
        raw = json.loads(text)
        state = review.import_bundle(json.dumps({"schema_version": "offline-scan-bundle-1.0",
            "site_plan": raw["base_plan"], "recording": raw["recording"]}))
        with self.assertRaisesRegex(ValueError, "at least one"):
            DerivedSiteReview.create(source, review.download_archive(state["workspace_revision"])["archive_text"])
        with TemporaryDirectory() as folder:
            store = DerivedReviewStore(Path(folder)/"review.json")
            for malformed in ('{"x":1,"x":2}', '{"x":NaN}', '['*2000+']'*2000):
                store.path.write_text(malformed)
                with self.assertRaises(ValueError): store.load()
            store.path.write_text("oversized")
            with patch("twinpulse_app.derived_site_review.MAX_DERIVED_BYTES", 3):
                with self.assertRaises(ValueError): store.load()


if __name__ == "__main__": unittest.main()
