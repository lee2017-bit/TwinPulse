# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic archive replay checks. No hardware, active project or Isaac."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_scan_review import route_bundle, bundle
from twinpulse_app.scan_review import ScanReview, MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ACTIONS
from twinpulse_core.revisions import canonical_sha256


def archive_fixture(map_overlay=True):
    text, _, _, pairs = route_bundle()
    service = ScanReview()
    state = service.import_bundle(text)
    state = service.propose(state["workspace_revision"], "obstacle", pairs)
    state = service.apply(state["workspace_revision"], state["proposal"]["revision"])
    if map_overlay:
        state = service.propose_map(state["workspace_revision"])
        state = service.apply_map(state["workspace_revision"], state["map_proposal"]["revision"])
    return service, state, service.export_archive(state["workspace_revision"])


class ScanArchiveTests(unittest.TestCase):
    def test_exact_text_transport_retains_digest_and_numeric_representation(self):
        service, state, archive = archive_fixture()
        packet = service.download_archive(state["workspace_revision"])
        transported = json.loads(json.dumps(packet))
        self.assertEqual(hashlib.sha256(transported["archive_text"].encode()).hexdigest(), transported["sha256"])
        self.assertEqual(json.loads(transported["archive_text"]), archive)
        new = ScanReview()
        restored = new.import_archive(new.snapshot()["workspace_revision"], transported["archive_text"])
        self.assertEqual(restored["scene"], state["scene"])
    def test_restore_correction_map_and_undo_preserves_geometry_not_approvals(self):
        service, state, archive = archive_fixture()
        new = ScanReview()
        restored = new.import_archive(new.snapshot()["workspace_revision"], json.dumps(archive))
        for key in ("scene", "before_scene", "scan", "edit_revision", "map_overlay", "route_conditions"):
            self.assertEqual(restored[key], state[key])
        self.assertNotEqual(restored["workspace_revision"], state["workspace_revision"])
        self.assertFalse(restored["motion_authorized"])
        self.assertFalse(restored["active_project_changed"])
        self.assertTrue(restored["review_required"])
        self.assertEqual(new.export_archive(restored["workspace_revision"]), archive)
        state = new.undo(restored["workspace_revision"], restored["edit_revision"])
        undo_archive = new.export_archive(state["workspace_revision"])
        again = ScanReview()
        replay = again.import_archive(again.snapshot()["workspace_revision"], json.dumps(undo_archive))
        self.assertEqual(replay["scene"], state["scene"])
        self.assertFalse(replay["map_present"])
        self.assertFalse(replay["mission_present"])
        self.assertIsNone(replay["edit_revision"])

    def test_pending_proposals_and_comparison_are_not_persisted(self):
        text, before, after, pairs = route_bundle()
        service = ScanReview()
        state = service.import_bundle(text)
        state = service.propose(state["workspace_revision"], "obstacle", pairs)
        state = service.compare(state["workspace_revision"], state["route_conditions"]["revision"], before, after)
        archive = service.export_archive(state["workspace_revision"])
        self.assertEqual(archive["actions"], [])
        restored = service.import_archive(state["workspace_revision"], json.dumps(archive))
        self.assertIsNone(restored["proposal"])
        self.assertIsNone(restored["route_comparison"])

    def test_tampering_even_with_rehashed_envelope_preserves_previous_workspace(self):
        service, state, archive = archive_fixture()
        for field, value in [("execution_authority", True), ("source_verified", True),
                              ("result_plan_revision", "a" * 64), ("extra", "ignored")]:
            bad = copy.deepcopy(archive); bad[field] = value
            bad["archive_digest"] = canonical_sha256({k: v for k, v in bad.items() if k != "archive_digest"})
            with self.assertRaises(ValueError):
                service.import_archive(state["workspace_revision"], json.dumps(bad))
            self.assertEqual(service.snapshot(), state)
        for mutation in (lambda a: a["actions"][0].update(proposal_revision="a" * 64),
                         lambda a: a["actions"][0].update(result_plan_revision="a" * 64),
                         lambda a: a["actions"][0].update(action="run"),
                         lambda a: a["actions"][0]["pairs"][0].update(beam_index=999),
                         lambda a: a["actions"].reverse()):
            bad = copy.deepcopy(archive); mutation(bad)
            bad["archive_digest"] = canonical_sha256({k: v for k, v in bad.items() if k != "archive_digest"})
            with self.assertRaises(ValueError):
                service.import_archive(state["workspace_revision"], json.dumps(bad))
            self.assertEqual(service.snapshot(), state)

    def test_stale_duplicate_nonfinite_oversize_and_capacity_rejected(self):
        service, state, archive = archive_fixture(False)
        with self.assertRaises(ValueError): service.export_archive("stale")
        for revision, text in [("stale", json.dumps(archive)), (state["workspace_revision"], '{"x":1,"x":2}'),
                              (state["workspace_revision"], '{"x":NaN}'),
                              (state["workspace_revision"], "x" * (MAX_ARCHIVE_BYTES + 1))]:
            with self.assertRaises(ValueError): service.import_archive(revision, text)
            self.assertEqual(service.snapshot(), state)
        bad = copy.deepcopy(archive); bad["actions"] *= MAX_ARCHIVE_ACTIONS + 1
        bad["archive_digest"] = canonical_sha256({k: v for k, v in bad.items() if k != "archive_digest"})
        with self.assertRaises(ValueError): service.import_archive(state["workspace_revision"], json.dumps(bad))
        with patch("twinpulse_app.scan_review.MAX_ARCHIVE_ACTIONS", 1):
            with self.assertRaises(ValueError): service.undo(state["workspace_revision"], state["edit_revision"])
        self.assertEqual(service.snapshot(), state)

    def test_import_reset_defensive_copy_and_changed_digest(self):
        service, state, archive = archive_fixture()
        archive["actions"].clear()
        self.assertEqual(len(service.export_archive(state["workspace_revision"])["actions"]), 2)
        with self.assertRaises(ValueError): service.import_archive(state["workspace_revision"], json.dumps(archive))
        text, _ = bundle()
        state = service.import_bundle(text)
        self.assertEqual(service.export_archive(state["workspace_revision"])["actions"], [])

    def test_workspace_changed_during_replay_is_not_overwritten(self):
        service, state, archive = archive_fixture()
        original = ScanReview.propose
        changed = []
        def concurrent_import(restored, *args):
            if not changed:
                text, _ = bundle()
                changed.append(service.import_bundle(text))
            return original(restored, *args)
        with patch.object(ScanReview, "propose", concurrent_import):
            with self.assertRaisesRegex(ValueError, "changed during"):
                service.import_archive(state["workspace_revision"], json.dumps(archive))
        self.assertEqual(service.snapshot(), changed[0])

    def test_deep_json_and_noncanonical_review_base_are_rejected(self):
        service, state, archive = archive_fixture()
        with self.assertRaises(ValueError):
            service.import_archive(state["workspace_revision"], "[" * 2000 + "]" * 2000)
        archive["base_plan"]["review_required"] = False
        archive["archive_digest"] = canonical_sha256({k: v for k, v in archive.items() if k != "archive_digest"})
        with self.assertRaises(ValueError):
            service.import_archive(state["workspace_revision"], json.dumps(archive))
        self.assertEqual(service.snapshot(), state)


if __name__ == "__main__": unittest.main()
