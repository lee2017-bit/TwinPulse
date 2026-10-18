# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from dataclasses import asdict, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_scan_correction import fixture
from twinpulse_core.map_refresh import propose_map_refresh, apply_map_refresh, undo_refreshed_correction
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.robot_profiles import compact_2wd_caster_profile
from twinpulse_core.scan_correction import propose_xy_correction, apply_xy_correction


def prepared(change=None, **kwargs):
    plan, recording, pairs = fixture(**kwargs)
    profile = compact_2wd_caster_profile()
    plan = replace(plan, robot=replace(plan.robot, profile_id=profile.id, profile_digest=canonical_sha256(asdict(profile))))
    if change:
        plan = change(plan)
    recording = replace(recording, scene_revision=plan.scene.revision, robot_profile_digest=plan.robot.profile_digest)
    proposal = propose_xy_correction(plan, recording, object_id="observed_box", pairs=pairs)
    applied = apply_xy_correction(plan, recording, proposal, reviewed_proposal_revision=proposal.revision)
    return applied, recording, profile


class MapRefreshTests(unittest.TestCase):
    def test_new_bindings_no_authority_and_determinism(self):
        applied, recording, profile = prepared()
        proposal = propose_map_refresh(applied.after, applied, recording, profile)
        self.assertEqual(proposal, propose_map_refresh(applied.after, applied, recording, profile))
        result = apply_map_refresh(applied.after, applied, recording, profile, proposal, reviewed_revision=proposal.revision)
        self.assertEqual(result.scene, applied.after.scene)
        self.assertEqual(result.navigation_map.scene_revision, result.scene.revision)
        self.assertEqual(result.mission.map_revision, result.navigation_map.revision)
        self.assertEqual(result.mission.start, applied.before.mission.start)
        self.assertEqual(result.mission.goal, applied.before.mission.goal)
        self.assertTrue(result.review_required)
        self.assertFalse(proposal.preview()["execution_authorized"])
        self.assertEqual(proposal.preview()["freed_cells"], 0)
        self.assertIsNone(applied.after.navigation_map)

    def test_no_unknown_or_occupied_cells_become_free(self):
        def change(plan):
            grid = replace(plan.navigation_map, cells=tuple(-1 if i % 2 else 100 for i in range(400)))
            return replace(plan, navigation_map=grid, mission=replace(plan.mission, map_revision=grid.revision))
        applied, recording, profile = prepared(change)
        grid = propose_map_refresh(applied.after, applied, recording, profile).candidate.navigation_map
        self.assertNotIn(0, grid.cells)
        self.assertIn(-1, grid.cells)

    def test_old_new_and_unobserved_boxes_are_occupied(self):
        applied, recording, profile = prepared()
        grid = propose_map_refresh(applied.after, applied, recording, profile).candidate.navigation_map
        for x, y in [(.5, .5), (1.7, 1.6), (3., 3.)]:
            self.assertEqual(grid.cell_at(x, y), 100)
        self.assertEqual(grid.cell_at(-4., -4.), 0)

    def test_rotated_box_aabb_is_conservative(self):
        applied, recording, profile = prepared(yaw=45)
        grid = propose_map_refresh(applied.after, applied, recording, profile).candidate.navigation_map
        self.assertEqual(grid.cell_at(.4, .4), 100)

    def test_wrong_review_tampered_proposal_and_stale_plan(self):
        applied, recording, profile = prepared()
        proposal = propose_map_refresh(applied.after, applied, recording, profile)
        with self.assertRaises(ValueError):
            apply_map_refresh(applied.after, applied, recording, profile, proposal, reviewed_revision="bad")
        tampered = replace(proposal, added_occupied_cells=0)
        with self.assertRaises(ValueError):
            apply_map_refresh(applied.after, applied, recording, profile, tampered, reviewed_revision=tampered.revision)
        with self.assertRaises(ValueError):
            propose_map_refresh(replace(applied.after, review_required=False), applied, recording, profile)

    def test_missing_or_stale_original_map_and_mission_rejected(self):
        for change in [lambda p: replace(p, navigation_map=None), lambda p: replace(p, mission=None),
                       lambda p: replace(p, mission=replace(p.mission, map_revision="a" * 64))]:
            applied, recording, profile = prepared(change)
            with self.assertRaises(ValueError):
                propose_map_refresh(applied.after, applied, recording, profile)

    def test_unsupported_dynamic_shape_and_floor_are_rejected(self):
        def dynamic(plan):
            objects = tuple(replace(o, dynamic=True, mass_kg=1.) if o.id == "unseen_box" else o for o in plan.scene.objects)
            scene = replace(plan.scene, objects=objects)
            grid = replace(plan.navigation_map, scene_revision=scene.revision)
            return replace(plan, scene=scene, navigation_map=grid,
                           mission=replace(plan.mission, scene_revision=scene.revision, map_revision=grid.revision))
        applied, recording, profile = prepared(dynamic)
        with self.assertRaisesRegex(ValueError, "static upright"):
            propose_map_refresh(applied.after, applied, recording, profile)
        def out_of_floor(plan):
            grid = replace(plan.navigation_map, origin_xy_m=(-6., -5.))
            return replace(plan, navigation_map=grid, mission=replace(plan.mission, map_revision=grid.revision))
        applied, recording, profile = prepared(out_of_floor)
        with self.assertRaisesRegex(ValueError, "floor bounds"):
            propose_map_refresh(applied.after, applied, recording, profile)

    def test_budget_exhaustion_rejects_without_partial_result(self):
        applied, recording, profile = prepared()
        with patch("twinpulse_core.map_refresh.MAX_CELL_WRITES", 1), self.assertRaisesRegex(ValueError, "budget"):
            propose_map_refresh(applied.after, applied, recording, profile)
        self.assertIsNone(applied.after.navigation_map)

    def test_undo_refreshed_geometry_discards_map_mission(self):
        applied, recording, profile = prepared()
        proposal = propose_map_refresh(applied.after, applied, recording, profile)
        undone = undo_refreshed_correction(proposal.candidate, applied, proposal, reviewed_edit_revision=applied.revision)
        self.assertEqual(undone.scene.objects, applied.before.scene.objects)
        self.assertNotEqual(undone.scene.revision, applied.before.scene.revision)
        self.assertIsNone(undone.navigation_map)
        self.assertIsNone(undone.mission)
        with self.assertRaises(ValueError):
            undo_refreshed_correction(applied.after, applied, proposal, reviewed_edit_revision=applied.revision)

    def test_changed_recording_or_profile_rejected(self):
        applied, recording, profile = prepared()
        with self.assertRaises(ValueError):
            propose_map_refresh(applied.after, applied, replace(recording, session_id="changed"), profile)
        with self.assertRaises(ValueError):
            propose_map_refresh(applied.after, applied, recording, replace(profile, max_linear_speed_mps=.2))


if __name__ == "__main__":
    unittest.main()
