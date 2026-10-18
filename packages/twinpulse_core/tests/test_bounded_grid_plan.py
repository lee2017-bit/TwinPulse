# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device tests for candidate planning; never physical clearance proof."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from twinpulse_core.bounded_grid_plan import NoBoundedPath, plan_bounded_grid


class BoundedGridPlanTests(unittest.TestCase):
    def test_open_path_is_exact_goal(self):
        self.assertEqual(plan_bounded_grid((0., -.7), (0., .4),
                                           (-1., 1., -1., 1.)), ((0., .4),))

    def test_disc_forces_bounded_detour_without_using_blocked_segment(self):
        start, goal = (0., -.7), (0., .5)
        path = plan_bounded_grid(start, goal, (-1., 1., -1., 1.),
                                 discs=((0., -.1, .08),))
        self.assertLessEqual(len(path), 16)
        self.assertEqual(path[-1], goal)
        self.assertTrue(any(abs(point[0]) > .3 for point in path[:-1]))
        for a, b in zip((start, *path[:-1]), path):
            for step in range(101):
                x = a[0] + (b[0] - a[0]) * step / 100
                y = a[1] + (b[1] - a[1]) * step / 100
                self.assertGreater(math.hypot(x, y + .1), .08 + .30 - .001)

    def test_blocked_goal_wall_and_budget_fail_closed(self):
        with self.assertRaisesRegex(NoBoundedPath, 'START_OR_GOAL_BLOCKED'):
            plan_bounded_grid((0., -.7), (0., .5), (-1., 1., -1., 1.),
                              discs=((0., .5, .1),))
        with self.assertRaisesRegex(NoBoundedPath, 'NO_PATH'):
            plan_bounded_grid((-.6, 0.), (.6, 0.), (-1., 1., -1., 1.),
                              boxes=((0., 0., .08, 1., 0.),))
        with self.assertRaisesRegex(NoBoundedPath, 'GRID_BUDGET_EXCEEDED'):
            plan_bounded_grid((0., -.7), (0., .5), (-1., 1., -1., 1.),
                              max_cells=20)

    def test_invalid_obstacles_and_nonfinite_input_fail_closed(self):
        for kwargs in ({'discs': ((0., 0., -1.),)},
                       {'boxes': ((0., 0., 1., 1., float('nan')),)}):
            with self.assertRaises(ValueError):
                plan_bounded_grid((0., -.7), (0., .5), (-1., 1., -1., 1.), **kwargs)
        with self.assertRaises(ValueError):
            plan_bounded_grid((float('nan'), 0.), (0., .5), (-1., 1., -1., 1.))

    def test_clear_exact_endpoint_uses_checked_adjacent_connector_when_nearest_blocked(self):
        start,goal=(-.34,0.),(.7,.7);bounds=(-1.,1.,-1.,1.)
        boxes=((- .1,0.,.01,.1,0.),)
        # The original endpoint has .23 m clearance; nearest grid (-.3,0)
        # has only .19 m. No start relocation or footprint reduction is allowed.
        with self.assertRaisesRegex(NoBoundedPath,'START_OR_GOAL_BLOCKED'):
            plan_bounded_grid((-.3,0.),goal,bounds,boxes,resolution=.1,clearance=.22)
        route=plan_bounded_grid(start,goal,bounds,boxes,resolution=.1,clearance=.22)
        self.assertEqual(route[-1],goal);self.assertGreater(len(route),1)
        self.assertEqual(plan_bounded_grid(start,goal,bounds,boxes,resolution=.1,clearance=.22,
            checked_route=route),route)
        # The same single search budget covers all endpoint connectors.
        with self.assertRaisesRegex(NoBoundedPath,'SEARCH_BUDGET_EXCEEDED'):
            plan_bounded_grid(start,goal,bounds,boxes,resolution=.1,clearance=.22,max_expansions=1)

    def test_no_valid_local_connector_unknown_and_disconnected_remain_blocked(self):
        bounds=(-1.,1.,-1.,1.)
        corridor=((- .68,0.,.1,.4,0.),(-.02,0.,.1,.4,0.))
        with self.assertRaisesRegex(NoBoundedPath,'SNAPPED_ENDPOINT_BLOCKED'):
            plan_bounded_grid((-.35,0.),(.65,0.),bounds,corridor,resolution=.1,clearance=.22)
        with self.assertRaisesRegex(NoBoundedPath,'NO_PATH'):
            plan_bounded_grid((-.65,0.),(.65,0.),bounds,((0.,0.,.02,1.,0.),),resolution=.1,clearance=.22)
        with self.assertRaisesRegex(NoBoundedPath,'START_OR_GOAL_BLOCKED'):
            plan_bounded_grid((-.34,0.),(.7,.7),bounds,resolution=.1,clearance=.22,observed_cells=[])

    def test_connector_search_validates_exact_goal_and_waypoint_budget(self):
        start,goal=(.7,.7),(-.34,0.);bounds=(-1.,1.,-1.,1.);boxes=((- .1,0.,.01,.1,0.),)
        route=plan_bounded_grid(start,goal,bounds,boxes,resolution=.1,clearance=.22)
        self.assertEqual(route[-1],goal)
        self.assertEqual(plan_bounded_grid(start,goal,bounds,boxes,resolution=.1,clearance=.22,checked_route=route),route)
        with self.assertRaisesRegex(NoBoundedPath,'WAYPOINT_BUDGET_EXCEEDED'):
            plan_bounded_grid(start,goal,bounds,boxes,resolution=.1,clearance=.22,max_waypoints=1)

    def test_explicit_large_sim_direct_path_preserves_default_grid_budget(self):
        bounds = (-5., 5., -6., 6.)
        with self.assertRaisesRegex(NoBoundedPath, 'GRID_BUDGET_EXCEEDED'):
            plan_bounded_grid((0., 0.), (0., .4), bounds, resolution=.10, clearance=.22)
        self.assertEqual(plan_bounded_grid((0., 0.), (0., .4), bounds,
            resolution=.10, clearance=.22, allow_direct_over_grid_budget=True), ((0., .4),))
        # A blocked direct path cannot obtain an unchecked route or a larger A* budget.
        with self.assertRaisesRegex(NoBoundedPath, 'GRID_BUDGET_EXCEEDED'):
            plan_bounded_grid((-.6, 0.), (.6, 0.), bounds,
                boxes=((0., 0., .08, .4, 0.),), resolution=.10, clearance=.22,
                allow_direct_over_grid_budget=True)

    def test_large_sim_direct_path_keeps_floor_obstacle_and_unknown_checks(self):
        bounds = (-5., 5., -6., 6.)
        for start, goal, extra, reason in (
            ((0., 0.), (5., 0.), {}, 'START_OR_GOAL_BLOCKED'),
            ((0., 0.), (0., .4), {'discs': ((0., .4, .1),)}, 'START_OR_GOAL_BLOCKED'),
            ((0., 0.), (0., .4), {'observed_cells': []}, 'START_OR_GOAL_BLOCKED'),
            ((0., 0.), (0., .4), {'boxes': ((0., .2, .02, .02, math.pi/4),)}, 'START_OR_GOAL_BLOCKED'),
        ):
            with self.subTest(reason=reason, extra=extra):
                with self.assertRaisesRegex(NoBoundedPath, reason):
                    plan_bounded_grid(start, goal, bounds, resolution=.10, clearance=.22,
                        allow_direct_over_grid_budget=True, **extra)
        with self.assertRaisesRegex(NoBoundedPath, 'SEGMENT_CHECK_BUDGET_EXCEEDED'):
            plan_bounded_grid((-90., 0.), (90., 0.), (-100., 100., -100., 100.),
                resolution=.02, allow_direct_over_grid_budget=True)
        with self.assertRaisesRegex(ValueError, 'GRID_PLAN_INPUT_INVALID'):
            plan_bounded_grid((0., 0.), (0., .4), bounds, allow_direct_over_grid_budget=1)


if __name__ == '__main__':
    unittest.main()
