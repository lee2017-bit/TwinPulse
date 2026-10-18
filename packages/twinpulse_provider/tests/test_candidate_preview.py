# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary rollback provenance tests; no provider/Isaac acceptance."""
from copy import deepcopy
import unittest
import test_budgeted_generation as fixtures
from twinpulse_core import canonical_sha256
from twinpulse_provider.candidate_preview import snapshot_preview, checked_preview_snapshot
from twinpulse_provider.semantic_scene import revision, compile_scene


class CandidatePreviewTests(unittest.TestCase):
    def test_rollback_keeps_exact_plan_receipt_and_marks_historical_image_static(self):
        draft = fixtures.draft()
        plan, _ = compile_scene(draft, fixtures.empty_observation(), fixtures.text_request())
        metadata = dict(candidate_revision=revision(draft), plan_sha256=canonical_sha256(plan),
                        scene_revision='historic-scene', physical_authority=False)
        progress = dict(candidate_revision=revision(draft), state='ready', rendered_count=1, pending_count=0)
        snapshot = snapshot_preview(draft, plan, {'metadata':metadata}, progress)
        restored = checked_preview_snapshot(draft, snapshot)
        self.assertEqual(restored['plan'], plan)
        self.assertEqual(restored['capture_metadata'], metadata)
        self.assertEqual(restored['progress']['state'], 'blocked')
        self.assertEqual(progress['state'], 'ready')
        failed = deepcopy(draft); failed['objects']['bed']['region'] = 'rear_right'
        self.assertIsNone(checked_preview_snapshot(failed, snapshot))

    def test_capture_of_another_candidate_or_plan_cannot_bind_to_best(self):
        draft = fixtures.draft()
        plan, _ = compile_scene(draft, fixtures.empty_observation(), fixtures.text_request())
        progress = dict(candidate_revision=revision(draft), state='ready')
        for metadata in (dict(candidate_revision='b'*64, plan_sha256=canonical_sha256(plan)),
                         dict(candidate_revision=revision(draft), plan_sha256='b'*64)):
            self.assertIsNone(snapshot_preview(draft, plan, {'metadata':metadata}, progress))


if __name__ == '__main__':
    unittest.main()
