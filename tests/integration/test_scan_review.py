# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from dataclasses import asdict
import math
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in ["packages/twinpulse_core/src", "packages/twinpulse_app/src", "packages/twinpulse_provider/src", "packages/twinpulse_core/tests"]:
    sys.path.insert(0, str(ROOT / path))
from test_scan_correction import fixture
from twinpulse_app.scan_review import MAX_BUNDLE_BYTES, ScanReview
from test_route_comparison import fixture as route_fixture, routes
from twinpulse_core.scan_recording import ScanFrame, ScanRecording, Transform2D


def bundle():
    plan, recording, pairs = fixture()
    text = json.dumps({"schema_version": "offline-scan-bundle-1.0", "site_plan": plan.to_dict(), "recording": recording.to_dict()})
    return text, json.loads(json.dumps([asdict(p) for p in pairs]))


def route_bundle():
    plan, profile = route_fixture()
    # Explicit synthetic rays for the two right-hand corners translated by (.1,.1).
    points = ((.35, -.15), (.35, .35))
    angles = [math.atan2(y, x) for x, y in points]
    frame = ScanFrame(1_000_000_000, "laser", "test_clock", angles[0], angles[1] - angles[0],
                      .05, 10., 0, tuple(math.hypot(x, y) for x, y in points),
                      Transform2D("laser", "world", 1_000_000_000, "test_clock", 0., 0., 0.))
    recording = ScanRecording(plan.scene.id, plan.scene.revision, plan.robot.profile_digest,
                              "synthetic_route_session", "test_clock", "synthetic", (frame,))
    text = json.dumps({"schema_version": "offline-scan-bundle-1.0", "site_plan": plan.to_dict(), "recording": recording.to_dict()})
    before, after = [json.loads(json.dumps({k: v for k, v in asdict(r).items() if k != "conditions_revision"})) for r in routes(plan, profile)]
    pairs = [{"frame_index": 0, "beam_index": i, "object_local_xy_m": [.25, y]} for i, y in enumerate([-.25, .25])]
    return text, before, after, pairs


class ScanReviewTests(unittest.TestCase):
    def test_reviewed_map_overlay_compare_and_undo(self):
        text, before, after, pairs = route_bundle()
        service = ScanReview()
        imported = service.import_bundle(text)
        state = service.propose(imported["workspace_revision"], "obstacle", pairs)
        state = service.apply(state["workspace_revision"], state["proposal"]["revision"])
        self.assertTrue(state["map_refresh_available"])
        state = service.propose_map(state["workspace_revision"])
        self.assertIsNone(state["route_conditions"])
        self.assertEqual(state["map_proposal"]["freed_cells"], 0)
        state = service.apply_map(state["workspace_revision"], state["map_proposal"]["revision"])
        self.assertNotEqual(state["route_conditions"]["revision"], imported["route_conditions"]["revision"])
        with self.assertRaises(ValueError):
            service.compare(state["workspace_revision"], imported["route_conditions"]["revision"], before, after)
        state = service.compare(state["workspace_revision"], state["route_conditions"]["revision"], before, after)
        self.assertTrue(state["route_comparison"]["comparable"])
        self.assertFalse(state["motion_authorized"])
        self.assertFalse(state["active_project_changed"])
        state = service.undo(state["workspace_revision"], state["edit_revision"])
        self.assertEqual(state["scene"]["objects"], imported["scene"]["objects"])
        self.assertFalse(state["map_present"])
        self.assertFalse(state["mission_present"])
        self.assertIsNone(state["route_comparison"])
        self.assertIsNone(state["map_overlay"])

    def test_map_overlay_wrong_review_stale_repeated_and_import_reset(self):
        text, _, _, pairs = route_bundle()
        service = ScanReview()
        state = service.import_bundle(text)
        with self.assertRaises(ValueError):
            service.propose_map(state["workspace_revision"])
        with self.assertRaises(ValueError):
            service.apply_map(state["workspace_revision"], "forged")
        state = service.propose(state["workspace_revision"], "obstacle", pairs)
        state = service.apply(state["workspace_revision"], state["proposal"]["revision"])
        state = service.propose_map(state["workspace_revision"])
        with self.assertRaises(ValueError):
            service.apply_map(state["workspace_revision"], "forged")
        self.assertEqual(service.snapshot(), state)
        applied = service.apply_map(state["workspace_revision"], state["map_proposal"]["revision"])
        with self.assertRaises(ValueError):
            service.apply_map(state["workspace_revision"], state["map_proposal"]["revision"])
        with self.assertRaises(ValueError):
            service.propose_map(applied["workspace_revision"])
        self.assertIsNone(service.import_bundle(text)["map_overlay"])

    def test_route_comparison_export_and_no_authority(self):
        text, before, after, _ = route_bundle()
        service = ScanReview()
        state = service.import_bundle(text)
        state = service.compare(state["workspace_revision"], state["route_conditions"]["revision"], before, after)
        result = state["route_comparison"]
        self.assertTrue(result["comparable"])
        self.assertEqual(result["shorter_route_id"], "candidate")
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(service.export_review()["snapshot"]["route_comparison"], result)
        result["baseline"]["length_m"] = -1
        self.assertEqual(service.snapshot()["route_comparison"]["baseline"]["length_m"], 8)
        self.assertFalse(state["active_project_changed"])

    def test_route_comparison_stale_and_shape_rejection_without_mutation(self):
        text, before, after, _ = route_bundle()
        service = ScanReview()
        state = service.import_bundle(text)
        revision = state["route_conditions"]["revision"]
        for workspace, conditions, bad in [("stale", revision, after), (state["workspace_revision"], "a" * 64, after),
                (state["workspace_revision"], revision, dict(after, execution_authorized=True)),
                (state["workspace_revision"], revision, dict(after, points_xy_m="bad")),
                (state["workspace_revision"], revision, dict(after, points_xy_m=[[True, 0], [2, 0]]))]:
            with self.assertRaises(ValueError):
                service.compare(workspace, conditions, before, bad)
            self.assertEqual(service.snapshot(), state)

    def test_route_comparison_invalidated_by_proposal_apply_undo_and_import(self):
        text, before, after, pairs = route_bundle()
        service = ScanReview()
        state = service.import_bundle(text)
        revision = state["route_conditions"]["revision"]
        state = service.compare(state["workspace_revision"], revision, before, after)
        state = service.propose(state["workspace_revision"], "obstacle", pairs)
        self.assertIsNone(state["route_comparison"])
        state = service.compare(state["workspace_revision"], revision, before, after)
        state = service.apply(state["workspace_revision"], state["proposal"]["revision"])
        self.assertIsNone(state["route_conditions"])
        self.assertIsNone(state["route_comparison"])
        with self.assertRaises(ValueError):
            service.compare(state["workspace_revision"], revision, before, after)
        state = service.undo(state["workspace_revision"], state["edit_revision"])
        self.assertIsNone(state["route_conditions"])
        state = service.import_bundle(text)
        state = service.compare(state["workspace_revision"], revision, before, after)
        self.assertIsNone(service.import_bundle(text)["route_comparison"])

    def test_unregistered_profile_cannot_be_compared(self):
        service = ScanReview()
        text, _ = bundle()
        state = service.import_bundle(text)
        self.assertIsNone(state["route_conditions"])
        self.assertIn("registry", state["route_unavailable_reason"])
        _, before, after, _ = route_bundle()
        with self.assertRaises(ValueError):
            service.compare(state["workspace_revision"], "a" * 64, before, after)

    def test_blocked_shorter_route_keeps_no_winner(self):
        text, before, after, _ = route_bundle()
        service = ScanReview()
        state = service.import_bundle(text)
        after["points_xy_m"] = [[-2., 0.], [2., 0.]]
        state = service.compare(state["workspace_revision"], state["route_conditions"]["revision"], before, after)
        self.assertIsNone(state["route_comparison"]["shorter_route_id"])
        self.assertFalse(state["route_comparison"]["comparable"])

    def test_initial_workspace_and_restart_empty(self):
        service = ScanReview()
        before = service.snapshot()
        self.assertIsNone(before["scene"])
        text, _ = bundle()
        service.import_bundle(text)
        self.assertIsNone(ScanReview().snapshot()["scene"])
        self.assertFalse(service.snapshot()["active_project_changed"])

    def test_import_propose_apply_undo_export(self):
        service = ScanReview()
        text, pairs = bundle()
        state = service.import_bundle(text)
        original = state["scene"]
        self.assertTrue(state["review_required"])
        state = service.propose(state["workspace_revision"], "observed_box", pairs)
        proposal_revision = state["proposal"]["revision"]
        state = service.apply(state["workspace_revision"], proposal_revision)
        self.assertFalse(state["map_present"])
        self.assertFalse(state["mission_present"])
        self.assertNotEqual(state["scene"]["revision"], original["revision"])
        export = service.export_review()
        self.assertFalse(export["execution_authority"])
        self.assertFalse(export["restore_supported"])
        state = service.undo(state["workspace_revision"], state["edit_revision"])
        self.assertEqual(state["scene"]["objects"], original["objects"])
        self.assertNotEqual(state["scene"]["revision"], original["revision"])
        self.assertIsNone(state["edit_revision"])
        self.assertFalse(state["motion_authorized"])
        self.assertFalse(state["demo_ready"])

    def test_stale_imported_workspace_and_second_apply_rejected(self):
        service = ScanReview()
        text, pairs = bundle()
        old = service.import_bundle(text)
        state = service.import_bundle(text)
        with self.assertRaises(ValueError):
            service.propose(old["workspace_revision"], "observed_box", pairs)
        state = service.propose(state["workspace_revision"], "observed_box", pairs)
        service.apply(state["workspace_revision"], state["proposal"]["revision"])
        with self.assertRaises(ValueError):
            service.apply(state["workspace_revision"], state["proposal"]["revision"])

    def test_bad_import_preserves_previous_workspace(self):
        service = ScanReview()
        text, _ = bundle()
        state = service.import_bundle(text)
        for bad in ["{", "[]", '{"x":1,"x":2}', '{"x":NaN}', "[" * 2000,
                    "x" * (MAX_BUNDLE_BYTES + 1), text.replace('"room"', '"other"', 1)]:
            with self.subTest(bad=bad[:20]), self.assertRaises(ValueError):
                service.import_bundle(bad)
            self.assertEqual(service.snapshot(), state)

    def test_unknown_fields_and_forged_history_not_imported(self):
        service = ScanReview()
        text, _ = bundle()
        for field in ["path", "applied", "motion_authorized", "command"]:
            value = json.loads(text)
            value[field] = "not allowed"
            with self.assertRaises(ValueError):
                service.import_bundle(json.dumps(value))

    def test_wrong_review_does_not_mutate(self):
        service = ScanReview()
        text, pairs = bundle()
        state = service.import_bundle(text)
        state = service.propose(state["workspace_revision"], "observed_box", pairs)
        with self.assertRaises(ValueError):
            service.apply(state["workspace_revision"], "bad")
        self.assertEqual(state, service.snapshot())
        state = service.apply(state["workspace_revision"], state["proposal"]["revision"])
        with self.assertRaises(ValueError):
            service.undo(state["workspace_revision"], "forged")
        self.assertEqual(state, service.snapshot())

    def test_snapshot_and_export_are_not_mutable_aliases(self):
        service = ScanReview()
        text, _ = bundle()
        service.import_bundle(text)
        before = service.snapshot()
        mutated = service.snapshot()
        mutated["scene"]["objects"][0]["id"] = "mutated"
        service.export_review()["reviewed_site_plan"]["scene"]["objects"][0]["id"] = "mutated"
        self.assertEqual(service.snapshot(), before)

    def test_pairs_shape_rejected(self):
        service = ScanReview()
        text, pairs = bundle()
        state = service.import_bundle(text)
        for bad in [[], pairs * 9, [dict(pairs[0], command="x"), pairs[1]], [dict(pairs[0], object_local_xy_m="1,2"), pairs[1]]]:
            with self.assertRaises(ValueError):
                service.propose(state["workspace_revision"], "observed_box", bad)
        self.assertEqual(service.snapshot(), state)

    def test_no_receipt_or_proposal_actions_fail(self):
        service = ScanReview()
        with self.assertRaises(ValueError):
            service.export_review()
        text, _ = bundle()
        state = service.import_bundle(text)
        with self.assertRaises(ValueError):
            service.apply(state["workspace_revision"], "a" * 64)
        with self.assertRaises(ValueError):
            service.undo(state["workspace_revision"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
