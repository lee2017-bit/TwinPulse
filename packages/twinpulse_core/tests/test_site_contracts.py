# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H2a isolated contract and negative fixtures; no engine or network calls."""

from dataclasses import asdict, replace
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from twinpulse_core.engine_contracts import CommandReceipt, SimulationSnapshot
from twinpulse_core.fixtures import fixed_warehouse_bundle
from twinpulse_core.models import Transform
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.site_contracts import (
    MissionSpecV2, NavigationMapRevision, ObservationBinding, RobotInstance, RunIntent, SceneRevision,
    SitePlan, STRAIGHT_CONTROLLER_CAPABILITY, evaluate_site_plan, import_legacy_bundle,
)
from twinpulse_core.validation import validate_bundle


def site_fixture():
    legacy = fixed_warehouse_bundle()
    scene = SceneRevision(legacy.scene.id, legacy.scene.objects, "photo", source_ref="a" * 64)
    navigation_map = NavigationMapRevision("map_main", scene.revision, 8, 6, 1.0, (-4.0, -3.0),
                                           (0,) * 48, "scene")
    robot = RobotInstance("robot_main", legacy.robot.id, canonical_sha256(asdict(legacy.robot)), legacy.task.start)
    mission = MissionSpecV2("route_main", scene.revision, robot.id, navigation_map.revision,
                            legacy.task.start, legacy.task.goal)
    plan = SitePlan(scene, navigation_map, robot, mission, review_required=False)
    run = RunIntent("run_main", scene.revision, navigation_map.revision, robot.id, mission.revision,
                    STRAIGHT_CONTROLLER_CAPABILITY, "demo_safety_v1")
    receipt = CommandReceipt("build_main", "build_scene", "default", "engine", "stage", "succeeded",
                             applied_revision=scene.revision, build_fingerprint="f" * 64)
    snapshot = SimulationSnapshot("engine", "stage", "default", scene.revision, None, 1, "built", None, None,
                                  ("get_state", "run"), ("simulation",))
    return legacy, plan, run, receipt, snapshot


class SiteContractTests(unittest.TestCase):
    def test_scene_only_is_valid_without_a_dummy_robot_or_mission(self):
        _, plan, _, _, _ = site_fixture()
        report = evaluate_site_plan(SitePlan(plan.scene))
        self.assertTrue(report.scene_valid)
        self.assertFalse(report.robot_compatible)
        self.assertFalse(report.mission_supported)
        self.assertFalse(report.run_allowed)

    def test_strict_roundtrip_and_digest_reject_mutation(self):
        _, plan, run, _, _ = site_fixture()
        self.assertEqual(SitePlan.from_dict(plan.to_dict()), plan)
        self.assertEqual(RunIntent.from_dict(run.to_dict()), run)
        modified = copy.deepcopy(plan.to_dict())
        modified["scene"]["objects"][0]["kind"] = "wall"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            SitePlan.from_dict(modified)
        extra = copy.deepcopy(plan.to_dict())
        extra["scene"]["objects"][0]["new_unreviewed_field"] = True
        with self.assertRaisesRegex(ValueError, "shape is unsupported"):
            SitePlan.from_dict(extra)
        unsupported = copy.deepcopy(plan.to_dict())
        unsupported["schema_version"] = "3.0"
        with self.assertRaisesRegex(ValueError, "version"):
            SitePlan.from_dict(unsupported)

    def test_valid_straight_mission_needs_current_receipt_and_capability(self):
        _, plan, run, receipt, snapshot = site_fixture()
        base = evaluate_site_plan(plan, profile=fixed_warehouse_bundle().robot)
        self.assertEqual((base.scene_valid, base.robot_compatible, base.mission_supported, base.run_allowed),
                         (True, True, True, False))
        trusted = dict(profile=fixed_warehouse_bundle().robot, run_intent=run, build_receipt=receipt,
                       snapshot=snapshot, engine_connected=True,
                       engine_session_id="engine", stage_epoch="stage",
                       controller_capabilities=frozenset({STRAIGHT_CONTROLLER_CAPABILITY}))
        self.assertTrue(evaluate_site_plan(plan, **trusted).run_allowed)
        self.assertFalse(evaluate_site_plan(plan, **{**trusted, "stage_epoch": "reconnected"}).run_allowed)
        self.assertFalse(evaluate_site_plan(plan, **{**trusted, "build_receipt": replace(receipt, status="failed")}).run_allowed)
        self.assertFalse(evaluate_site_plan(plan, **{**trusted, "controller_capabilities": frozenset()}).run_allowed)
        self.assertFalse(evaluate_site_plan(plan, **{**trusted, "engine_connected": False}).run_allowed)
        self.assertFalse(evaluate_site_plan(plan, **{**trusted, "snapshot": replace(snapshot, applied_revision="a" * 64)}).run_allowed)
        self.assertFalse(evaluate_site_plan(plan, **{**trusted, "snapshot": replace(snapshot, permitted_commands=("get_state",))}).run_allowed)
        self.assertFalse(evaluate_site_plan(plan, **{**trusted, "run_intent": replace(run, safety_policy_id="unreviewed")}).run_allowed)

    def test_unknown_or_occupied_map_and_stale_map_refuse_mission(self):
        _, plan, _, _, _ = site_fixture()
        for occupancy in (-1, 100):
            cells = list(plan.navigation_map.cells)
            cells[3 * 8 + 5] = occupancy  # goal x=1.5, y=0
            blocked_map = replace(plan.navigation_map, cells=tuple(cells))
            blocked_mission = replace(plan.mission, map_revision=blocked_map.revision)
            report = evaluate_site_plan(replace(plan, navigation_map=blocked_map, mission=blocked_mission),
                                        profile=fixed_warehouse_bundle().robot)
            self.assertTrue(report.scene_valid)
            self.assertFalse(report.mission_supported)
            self.assertIn("mission_blocked_or_unknown", report.reasons)
        stale = evaluate_site_plan(replace(plan, navigation_map=replace(plan.navigation_map,
                                         scene_revision="b" * 64)), profile=fixed_warehouse_bundle().robot)
        self.assertFalse(stale.mission_supported)
        adjacent_cells = list(plan.navigation_map.cells)
        adjacent_cells[2 * 8 + 4] = 100  # outside centerline, inside robot's swept footprint
        adjacent_map = replace(plan.navigation_map, cells=tuple(adjacent_cells))
        adjacent_mission = replace(plan.mission, map_revision=adjacent_map.revision)
        self.assertFalse(evaluate_site_plan(replace(plan, navigation_map=adjacent_map, mission=adjacent_mission),
                                            profile=fixed_warehouse_bundle().robot).mission_supported)

    def test_reverse_waypoint_off_floor_and_wrong_profile_are_not_drivable(self):
        _, plan, _, _, _ = site_fixture()
        profile = fixed_warehouse_bundle().robot
        variants = (
            replace(plan.mission, goal=Transform((-1.0, 0.0, 0.0))),
            replace(plan.mission, waypoints=(Transform((0.5, 1.0, 0.0)),)),
            replace(plan.mission, goal=Transform((30.0, 0.0, 0.0))),
        )
        for mission in variants:
            report = evaluate_site_plan(replace(plan, mission=mission), profile=profile)
            self.assertTrue(report.scene_valid)
            self.assertFalse(report.mission_supported)
            self.assertFalse(report.run_allowed)
        wrong = evaluate_site_plan(replace(plan, robot=replace(plan.robot, profile_digest="b" * 64)), profile=profile)
        self.assertFalse(wrong.robot_compatible)
        self.assertFalse(wrong.mission_supported)

    def test_legacy_import_is_explicit_review_only_and_preserves_v1(self):
        legacy = fixed_warehouse_bundle()
        imported = import_legacy_bundle(legacy)
        self.assertEqual(imported.scene.source, "legacy")
        self.assertTrue(imported.review_required)
        self.assertIsNone(imported.navigation_map)
        self.assertFalse(evaluate_site_plan(imported, profile=legacy.robot).run_allowed)
        self.assertEqual(validate_bundle(legacy), legacy)

    def test_map_rejects_implicit_free_unknown_and_oversize(self):
        _, plan, _, _, _ = site_fixture()
        with self.assertRaisesRegex(ValueError, "cells"):
            replace(plan.navigation_map, cells=(0,) * 47)
        with self.assertRaisesRegex(ValueError, "cells"):
            replace(plan.navigation_map, cells=(0,) * 47 + (False,))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            replace(plan.navigation_map, width=1024, height=1024)
        self.assertEqual(plan.navigation_map.cell_at(100, 100), -1)

    def test_robot_observation_cannot_also_be_a_static_scene_object(self):
        _, plan, _, _, _ = site_fixture()
        scene = replace(plan.scene, observation_bindings=(ObservationBinding("observed_agv", "box_demo"),))
        robot = replace(plan.robot, observation_id="observed_agv")
        with self.assertRaisesRegex(ValueError, "both the mobile robot and a scene object"):
            SitePlan(scene, robot=robot)


if __name__ == "__main__":
    unittest.main()
