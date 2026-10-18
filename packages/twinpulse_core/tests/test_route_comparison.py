# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from dataclasses import asdict, replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from twinpulse_core.models import SceneObject, ShapeSpec, Transform
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.robot_profiles import compact_2wd_caster_profile
from twinpulse_core.route_comparison import RouteCandidate, compare_routes, comparison_conditions
from twinpulse_core.site_contracts import MissionSpecV2, NavigationMapRevision, RobotInstance, SceneRevision, SitePlan


def fixture():
    profile = compact_2wd_caster_profile()
    scene = SceneRevision("route_room", (
        SceneObject("floor", "floor", Transform((0., 0., -.05)), ShapeSpec("box", (10., 10., .1))),
        SceneObject("obstacle", "box", Transform((0., 0., .5)), ShapeSpec("box", (.5, .5, 1.))),
    ), "manual")
    cells = [0] * 1600
    for row in (19, 20):
        for col in (19, 20):
            cells[row * 40 + col] = 100
    grid = NavigationMapRevision("route_grid", scene.revision, 40, 40, .25, (-5., -5.), tuple(cells), "scene")
    start, goal = Transform((-2., 0., .1)), Transform((2., 0., .1))
    robot = RobotInstance("robot", profile.id, canonical_sha256(asdict(profile)), start)
    mission = MissionSpecV2("route_mission", scene.revision, robot.id, grid.revision, start, goal)
    plan = SitePlan(scene, grid, robot, mission)
    return plan, profile


def routes(plan, profile, clearance=.05):
    revision = comparison_conditions(plan, profile, clearance_m=clearance)["revision"]
    return (RouteCandidate("baseline", revision, ((-2., 0.), (-2., 2.), (2., 2.), (2., 0.)), "synthetic"),
            RouteCandidate("candidate", revision, ((-2., 0.), (-1., 1.), (1., 1.), (2., 0.)), "synthetic"))


def regrid(plan, grid):
    return replace(plan, navigation_map=grid, mission=replace(plan.mission, map_revision=grid.revision))


class RouteComparisonTests(unittest.TestCase):
    def test_known_lengths_and_unverified_geometry_only(self):
        plan, profile = fixture()
        result = compare_routes(plan, profile, *routes(plan, profile))
        self.assertTrue(result["comparable"])
        self.assertEqual(result["baseline"]["length_m"], 8)
        self.assertAlmostEqual(result["candidate"]["length_m"], 2 + 2 * math.sqrt(2))
        self.assertEqual(result["shorter_route_id"], "candidate")
        for name in ("source_verified", "execution_authorized", "demo_ready"):
            self.assertFalse(result[name])
        self.assertIsNone(result["travel_time_improvement"])
        self.assertIsNone(result["collision_improvement"])

    def test_shorter_blocked_route_is_not_a_winner(self):
        plan, profile = fixture()
        before, after = routes(plan, profile)
        result = compare_routes(plan, profile, before, replace(after, points_xy_m=((-2., 0.), (2., 0.))))
        self.assertFalse(result["comparable"])
        self.assertEqual(result["candidate"]["grid_check"]["reason"], "occupied_cell")
        self.assertIsNone(result["shorter_route_id"])
        self.assertIsNone(result["candidate_length_reduction_percent"])

    def test_unknown_is_not_free(self):
        plan, profile = fixture()
        cells = tuple(-1 if c == 100 else c for c in plan.navigation_map.cells)
        plan = regrid(plan, replace(plan.navigation_map, cells=cells))
        before, after = routes(plan, profile)
        result = compare_routes(plan, profile, before, replace(after, points_xy_m=((-2., 0.), (2., 0.))))
        self.assertEqual(result["candidate"]["grid_check"]["reason"], "unknown_cell")
        self.assertFalse(result["comparable"])

    def test_midsegment_thin_obstacle_not_missed(self):
        plan, profile = fixture()
        cells = [0] * (800 * 200)
        cells[100 * 800 + 400] = 100
        grid = NavigationMapRevision("fine_grid", plan.scene.revision, 800, 200, .01, (-4., -1.), tuple(cells), "scene")
        plan = regrid(plan, grid)
        before, after = routes(plan, profile)
        straight = replace(after, points_xy_m=((-2., 0.), (2., 0.)))
        result = compare_routes(plan, profile, before, straight)
        self.assertEqual(result["candidate"]["grid_check"]["reason"], "occupied_cell")

    def test_footprint_clearance_blocks_near_wall_and_touch(self):
        plan, profile = fixture()
        before, after = routes(plan, profile)
        radius = comparison_conditions(plan, profile)["inflation_m"]
        for y in [.3, .25 + radius]:
            result = compare_routes(plan, profile, before, replace(after, points_xy_m=((-2., 0.), (-2., y), (2., y), (2., 0.))))
            self.assertFalse(result["comparable"])
        y = .25 + radius + .001
        result = compare_routes(plan, profile, before, replace(after, points_xy_m=((-2., 0.), (-2., y), (2., y), (2., 0.))))
        self.assertTrue(result["comparable"])

    def test_outside_grid_never_free(self):
        plan, profile = fixture()
        before, after = routes(plan, profile)
        for x in [-5., -4.8, -99.]:
            result = compare_routes(plan, profile, before, replace(after, points_xy_m=((-2., 0.), (x, 2.), (2., 0.))))
            self.assertEqual(result["candidate"]["grid_check"]["reason"], "footprint_outside_or_touching_grid")

    def test_exact_endpoint_equality(self):
        plan, profile = fixture()
        before, after = routes(plan, profile)
        for points in [((-1.9, 0.), (2., 0.)), ((-2., 0.), (2.01, 0.)), ((2., 0.), (-2., 0.))]:
            with self.assertRaisesRegex(ValueError, "start and goal"):
                compare_routes(plan, profile, before, replace(after, points_xy_m=points))

    def test_changed_conditions_cannot_be_compared(self):
        plan, profile = fixture()
        before, after = routes(plan, profile)
        with self.assertRaisesRegex(ValueError, "conditions"):
            compare_routes(plan, profile, before, after, clearance_m=.1)
        with self.assertRaises(ValueError):
            compare_routes(plan, profile, before, replace(after, conditions_revision="a" * 64))
        changed = regrid(plan, replace(plan.navigation_map, cells=(0,) * 1600))
        with self.assertRaises(ValueError):
            compare_routes(changed, profile, before, after)

    def test_missing_stale_dependencies_and_profile(self):
        plan, profile = fixture()
        for changed in [replace(plan, navigation_map=None), replace(plan, mission=None), replace(plan, robot=None),
                        replace(plan, navigation_map=replace(plan.navigation_map, scene_revision="c" * 64)),
                        replace(plan, mission=replace(plan.mission, map_revision="c" * 64)),
                        replace(plan, robot=replace(plan.robot, profile_digest="c" * 64)),
                        replace(plan, mission=replace(plan.mission, robot_instance_id="other"))]:
            with self.assertRaises(ValueError):
                comparison_conditions(changed, profile)
        with self.assertRaises(ValueError):
            comparison_conditions(plan, replace(profile, max_linear_speed_mps=.2))

    def test_planar_and_waypoint_restrictions(self):
        plan, profile = fixture()
        for mission in [replace(plan.mission, waypoints=(Transform((0., 2., .1)),)),
                        replace(plan.mission, goal=Transform((2., 0., .2))),
                        replace(plan.mission, goal=Transform((2., 0., .1), (2., 0., 0.)))]:
            with self.assertRaises(ValueError):
                comparison_conditions(replace(plan, mission=mission), profile)

    def test_finite_strict_bounded_route_points(self):
        for points in [(), ((0., 0.),), ((0., 0.),) * 129, ((0., 0.), (0., 0.)),
                       ((True, 0.), (1., 0.)), ((0., 0.), (float("nan"), 0.)),
                       ((0., 0.), (float("inf"), 0.)), ((0., 0.), (101., 0.)), [[0., 0.], [1., 0.]]]:
            with self.assertRaises(ValueError):
                RouteCandidate("bad", "a" * 64, points)

    def test_clearance_type_bounds(self):
        plan, profile = fixture()
        for clearance in [-.1, 1.1, True, float("nan"), float("inf"), "0.05"]:
            with self.assertRaises(ValueError):
                comparison_conditions(plan, profile, clearance_m=clearance)

    def test_budget_exhaustion_is_not_clear(self):
        plan, profile = fixture()
        with patch("twinpulse_core.route_comparison.MAX_CELL_CHECKS", 1):
            result = compare_routes(plan, profile, *routes(plan, profile))
        self.assertFalse(result["comparable"])
        self.assertEqual(result["baseline"]["grid_check"]["status"], "EVALUATION_LIMIT")

    def test_tie_and_baseline_shorter(self):
        plan, profile = fixture()
        before, after = routes(plan, profile)
        result = compare_routes(plan, profile, before, replace(after, points_xy_m=before.points_xy_m))
        self.assertEqual(result["shorter_route_id"], "tie")
        self.assertEqual(result["candidate_length_reduction_percent"], 0)
        result = compare_routes(plan, profile, replace(after, id="baseline"), replace(before, id="candidate"))
        self.assertEqual(result["shorter_route_id"], "baseline")
        self.assertLess(result["candidate_length_reduction_m"], 0)

    def test_distinct_ids_and_explicit_provenance(self):
        plan, profile = fixture()
        before, after = routes(plan, profile)
        with self.assertRaises(ValueError):
            compare_routes(plan, profile, before, replace(after, id="baseline"))
        with self.assertRaises(ValueError):
            replace(after, provenance="verified_physical")

    def test_footprint_covers_passive_and_drive_wheels(self):
        plan, profile = fixture()
        radius = comparison_conditions(plan, profile)["footprint_radius_m"]
        self.assertGreaterEqual(radius, math.hypot(*profile.chassis_dimensions_m[:2]) / 2)
        for wheel in profile.support_wheels:
            self.assertGreaterEqual(radius, math.hypot(*wheel.position_xy_m) + wheel.radius_m)
        self.assertGreaterEqual(radius, math.hypot(profile.wheel_radius_m, profile.wheel_track_m / 2 + profile.wheel_width_m / 2))

    def test_deterministic_and_input_unchanged(self):
        plan, profile = fixture()
        original = plan.to_dict()
        before, after = routes(plan, profile)
        self.assertEqual(compare_routes(plan, profile, before, after), compare_routes(plan, profile, before, after))
        self.assertEqual(plan.to_dict(), original)


if __name__ == "__main__":
    unittest.main()
