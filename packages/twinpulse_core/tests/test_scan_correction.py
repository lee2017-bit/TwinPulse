# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from twinpulse_core.models import SceneObject, ShapeSpec, Transform
from twinpulse_core.scan_correction import (LandmarkPair, apply_xy_correction, plan_revision,
                                          propose_xy_correction, undo_xy_correction)
from twinpulse_core.scan_recording import ScanFrame, ScanRecording, Transform2D
from twinpulse_core.site_contracts import (MissionSpecV2, NavigationMapRevision, RobotInstance,
                                          SceneRevision, SitePlan, evaluate_site_plan)


def fixture(*, delta=(.2, .1), yaw=0, provenance="synthetic"):
    objects = (
        SceneObject("floor", "floor", Transform((0., 0., -.05)), ShapeSpec("box", (10., 10., .1))),
        SceneObject("observed_box", "box", Transform((1., 1., 1.), (0., 0., float(yaw))), ShapeSpec("box", (1., 1., 2.))),
        SceneObject("unseen_box", "box", Transform((3., 3., .5)), ShapeSpec("box", (1., 1., 1.))),
    )
    scene = SceneRevision("room", objects, "photo", "a" * 64)
    robot = RobotInstance("robot", "burger", "b" * 64, Transform((0., 0., .1)))
    grid = NavigationMapRevision("grid", scene.revision, 20, 20, .5, (-5., -5.), (0,) * 400, "scene")
    mission = MissionSpecV2("mission", scene.revision, robot.id, grid.revision,
                            robot.initial_pose, Transform((3., 0., .1)))
    plan = SitePlan(scene, grid, robot, mission, review_required=False)
    # Two manually labelled box corners, generated with known translation.
    landmarks = []
    for lx, ly in [(-.5, -.5), (.5, -.5)]:
        x = 1 + math.cos(math.radians(yaw)) * lx - math.sin(math.radians(yaw)) * ly + delta[0]
        y = 1 + math.sin(math.radians(yaw)) * lx + math.cos(math.radians(yaw)) * ly + delta[1]
        landmarks.append((math.atan2(y, x), math.hypot(x, y), (lx, ly)))
    landmarks.sort()
    frame = ScanFrame(1_000_000_000, "laser", "test_clock", landmarks[0][0],
                      landmarks[1][0] - landmarks[0][0], .05, 10., 0,
                      tuple(item[1] for item in landmarks),
                      Transform2D("laser", "world", 1_000_000_000, "test_clock", 0., 0., 0.))
    recording = ScanRecording("room", scene.revision, robot.profile_digest, "test_session",
                              "test_clock", provenance, (frame,))
    pairs = tuple(LandmarkPair(0, i, item[2]) for i, item in enumerate(landmarks))
    return plan, recording, pairs


def proposal(plan, recording, pairs):
    return propose_xy_correction(plan, recording, object_id="observed_box", pairs=pairs)


class ScanCorrectionTests(unittest.TestCase):
    def test_known_translation_recovered_without_mutation(self):
        plan, recording, pairs = fixture()
        before = plan.to_dict()
        edit = proposal(plan, recording, pairs)
        self.assertAlmostEqual(edit.delta_xy_m[0], .2)
        self.assertAlmostEqual(edit.delta_xy_m[1], .1)
        self.assertLess(edit.max_residual_m, 1e-12)
        self.assertEqual(plan.to_dict(), before)

    def test_rotated_box_local_landmarks_keep_rotation(self):
        plan, recording, pairs = fixture(yaw=90)
        edit = proposal(plan, recording, pairs)
        result = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision)
        self.assertAlmostEqual(result.after.scene.objects[1].transform.position_m[0], 1.2)
        self.assertEqual(result.after.scene.objects[1].transform.rotation_rpy_deg, (0., 0., 90))

    def test_apply_preserves_z_shape_ids_flags_and_unobserved_objects(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        result = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision)
        self.assertEqual(result.before, plan)
        self.assertEqual(result.after.scene.objects[0], plan.scene.objects[0])
        self.assertEqual(result.after.scene.objects[2], plan.scene.objects[2])
        before, after = plan.scene.objects[1], result.after.scene.objects[1]
        self.assertEqual(replace(after, transform=before.transform), before)
        self.assertEqual(before.transform.position_m[2], after.transform.position_m[2])
        self.assertEqual(result.after.scene.parent_revision, plan.scene.revision)
        self.assertEqual(result.after.scene.source, "manual")
        self.assertEqual(result.after.scene.source_ref, edit.revision)

    def test_apply_invalidates_map_mission_review_and_old_revision(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        after = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision).after
        self.assertIsNone(after.navigation_map)
        self.assertIsNone(after.mission)
        self.assertTrue(after.review_required)
        self.assertEqual(after.robot, plan.robot)
        self.assertNotEqual(after.scene.revision, plan.scene.revision)
        self.assertFalse(evaluate_site_plan(after).run_allowed)
        with self.assertRaises(ValueError):
            apply_xy_correction(after, recording, edit, reviewed_proposal_revision=edit.revision)

    def test_undo_restores_geometry_not_old_authority(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        applied = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision)
        restored = undo_xy_correction(applied.after, applied, reviewed_edit_revision=applied.revision)
        self.assertEqual(restored.scene.objects, plan.scene.objects)
        self.assertEqual(restored.scene.observation_bindings, plan.scene.observation_bindings)
        self.assertEqual(restored.scene.parent_revision, applied.after.scene.revision)
        self.assertNotEqual(restored.scene.revision, plan.scene.revision)
        self.assertNotEqual(restored.scene.revision, applied.after.scene.revision)
        self.assertIsNone(restored.navigation_map)
        self.assertIsNone(restored.mission)
        self.assertTrue(restored.review_required)
        self.assertFalse(evaluate_site_plan(restored).run_allowed)
        with self.assertRaises(ValueError):
            undo_xy_correction(restored, applied, reviewed_edit_revision=applied.revision)

    def test_exact_review_digest_required_for_apply_and_undo(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        for reviewed in ["", "a" * 64, True, None]:
            with self.assertRaises(ValueError):
                apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=reviewed)
        applied = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision)
        with self.assertRaises(ValueError):
            undo_xy_correction(applied.after, applied, reviewed_edit_revision=edit.revision)

    def test_scene_robot_mission_and_review_changes_make_proposal_stale(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        for changed in [replace(plan, review_required=True), replace(plan, mission=None),
                        replace(plan, robot=replace(plan.robot, id="other_robot")),
                        replace(plan, scene=replace(plan.scene, source="manual"))]:
            with self.assertRaisesRegex(ValueError, "stale"):
                apply_xy_correction(changed, recording, edit, reviewed_proposal_revision=edit.revision)

    def test_undo_cannot_overwrite_intervening_edits(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        applied = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision)
        changed = replace(applied.after, review_required=False)
        with self.assertRaisesRegex(ValueError, "stale"):
            undo_xy_correction(changed, applied, reviewed_edit_revision=applied.revision)

    def test_tampered_proposal_recomputed_not_trusted(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        for changed in [replace(edit, delta_xy_m=(.3, .3)), replace(edit, max_residual_m=.02),
                        replace(edit, policy_id="other_policy"), replace(edit, provenance="recorded_sensor")]:
            with self.assertRaises(ValueError):
                apply_xy_correction(plan, recording, changed, reviewed_proposal_revision=changed.revision)

    def test_changed_recording_rejected_at_apply(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        changed = replace(recording, session_id="different_session")
        with self.assertRaises(ValueError):
            apply_xy_correction(plan, changed, edit, reviewed_proposal_revision=edit.revision)

    def test_site_revision_profile_and_missing_robot_binding(self):
        plan, recording, pairs = fixture()
        for changed in [replace(recording, site_id="other"), replace(recording, scene_revision="c" * 64),
                        replace(recording, robot_profile_digest="c" * 64)]:
            with self.assertRaises(ValueError):
                proposal(plan, changed, pairs)
        with self.assertRaises(ValueError):
            proposal(replace(plan, robot=None), recording, pairs)

    def test_missing_unknown_and_duplicate_correspondences(self):
        plan, recording, pairs = fixture()
        for bad in [(), pairs[:1], pairs * 9, list(pairs), (pairs[0], pairs[0]),
                    (replace(pairs[0], frame_index=99), pairs[1]),
                    (replace(pairs[0], beam_index=99), pairs[1]),
                    (replace(pairs[0], object_local_xy_m=pairs[1].object_local_xy_m), pairs[1])]:
            with self.subTest(pairs=bad), self.assertRaises(ValueError):
                proposal(plan, recording, bad)
        frame = replace(recording.frames[0], ranges_m=(None, recording.frames[0].ranges_m[1]))
        with self.assertRaises(ValueError):
            proposal(plan, replace(recording, frames=(frame,)), pairs)

    def test_multiple_frames_not_combined_as_stationary_landmarks(self):
        plan, recording, pairs = fixture()
        f = recording.frames[0]
        second = replace(f, stamp_ns=f.stamp_ns + 100_000_000,
                         world_from_sensor=replace(f.world_from_sensor, stamp_ns=f.stamp_ns + 100_000_000))
        recording = replace(recording, frames=(f, second))
        with self.assertRaises(ValueError):
            proposal(plan, recording, (pairs[0], replace(pairs[1], frame_index=1)))

    def test_floor_missing_dynamic_noncollision_and_tilted_object_rejected(self):
        plan, recording, pairs = fixture()
        for object_id in ["floor", "missing", "robot"]:
            with self.assertRaises(ValueError):
                propose_xy_correction(plan, recording, object_id=object_id, pairs=pairs)
        obj = plan.scene.objects[1]
        for bad in [replace(obj, dynamic=True, mass_kg=1.), replace(obj, collision=False),
                    replace(obj, transform=replace(obj.transform, rotation_rpy_deg=(10., 0., 0.)))]:
            changed = replace(plan, scene=replace(plan.scene, objects=(plan.scene.objects[0], bad, plan.scene.objects[2])))
            with self.assertRaises(ValueError):
                proposal(changed, replace(recording, scene_revision=changed.scene.revision), pairs)

    def test_perimeter_not_centre_or_outside(self):
        plan, recording, pairs = fixture()
        for local in [(0., 0.), (.6, -.5), (.5, .6)]:
            with self.assertRaises(ValueError):
                proposal(plan, recording, (replace(pairs[0], object_local_xy_m=local), pairs[1]))

    def test_outlier_or_wrong_pair_rejected_without_relaxing_policy(self):
        plan, recording, pairs = fixture()
        frame = recording.frames[0]
        frame = replace(frame, ranges_m=(frame.ranges_m[0] + .3, frame.ranges_m[1]))
        with self.assertRaisesRegex(ValueError, "consistent"):
            proposal(plan, replace(recording, frames=(frame,)), pairs)
        with self.assertRaises(ValueError):
            proposal(plan, recording, (replace(pairs[0], object_local_xy_m=pairs[1].object_local_xy_m),
                                       replace(pairs[1], object_local_xy_m=pairs[0].object_local_xy_m)))

    def test_large_and_zero_translations_rejected(self):
        for delta in [(0., 0.), (.5, .1), (2., 0.)]:
            plan, recording, pairs = fixture(delta=delta)
            with self.assertRaisesRegex(ValueError, "translation"):
                proposal(plan, recording, pairs)

    def test_nearby_landmarks_insufficient(self):
        plan, recording, pairs = fixture()
        f = recording.frames[0]
        narrow = replace(f, angle_increment_rad=.00001, ranges_m=(1., 1.))
        bad = (LandmarkPair(0, 0, (.5, -.5)), LandmarkPair(0, 1, (.5, -.49)))
        with self.assertRaisesRegex(ValueError, "span"):
            proposal(plan, replace(recording, frames=(narrow,)), bad)

    def test_landmark_numeric_types(self):
        for local in [(True, 0.), (float("nan"), 0.), (float("inf"), 0.), [0., 0.], (0.,)]:
            with self.assertRaises(ValueError):
                LandmarkPair(0, 0, local)
        for index in [-1, True, 1.0]:
            with self.assertRaises(ValueError):
                LandmarkPair(index, 0, (0., 0.))

    def test_provenance_does_not_grant_physical_authority(self):
        for source in ["synthetic", "simulation", "recorded_sensor"]:
            plan, recording, pairs = fixture(provenance=source)
            preview = proposal(plan, recording, pairs).preview()
            self.assertEqual(preview["provenance"], source)
            self.assertEqual(preview["physical_validation"], "NOT_RUN")
            for key in ["source_verified", "alignment_verified", "motion_authorized", "demo_ready"]:
                self.assertIs(preview[key], False)

    def test_plan_and_edit_hashes_deterministic(self):
        plan, recording, pairs = fixture()
        edit = proposal(plan, recording, pairs)
        self.assertEqual(edit.revision, proposal(plan, recording, pairs).revision)
        a = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision)
        b = apply_xy_correction(plan, recording, edit, reviewed_proposal_revision=edit.revision)
        self.assertEqual(a.revision, b.revision)
        self.assertEqual(plan_revision(SitePlan.from_dict(a.after.to_dict())), plan_revision(a.after))

    def test_nonpersistent_parent_digest_rejected(self):
        plan, recording, pairs = fixture()
        obj = plan.scene.objects[1]
        bad = replace(obj, transform=replace(obj.transform, rotation_rpy_deg=(0, 0, 0)))
        scene = replace(plan.scene, objects=(plan.scene.objects[0], bad, plan.scene.objects[2]))
        with self.assertRaisesRegex(ValueError, "digest"):
            proposal(replace(plan, scene=scene), replace(recording, scene_revision=scene.revision), pairs)


if __name__ == "__main__":
    unittest.main()
