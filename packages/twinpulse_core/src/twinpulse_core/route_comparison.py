# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Same-condition geometric polyline comparison, not planning or execution.

Checks continuous segments against a supplied occupancy grid with a conservative
orientation-independent footprint. Unknown/outside cells are never free. No claim
that the grid is truthful, the controller can follow the route, or time improved.
"""
from dataclasses import asdict, dataclass
import math

from .models import RobotProfile
from .revisions import canonical_sha256
from .site_contracts import SitePlan
from .validation import validate_robot_profile

POLICY_ID = "offline_grid_polyline_v1"
MAX_CELL_CHECKS = 200_000
EPS = 1e-9


def comparison_conditions(plan: SitePlan, profile: RobotProfile, *, clearance_m=.05) -> dict:
    SitePlan.from_dict(plan.to_dict())
    validate_robot_profile(profile)
    grid, robot, mission = plan.navigation_map, plan.robot, plan.mission
    profile_digest = canonical_sha256(asdict(profile))
    if not grid or not robot or not mission:
        raise ValueError("comparison requires a map, robot profile and mission")
    if (grid.scene_revision != plan.scene.revision or mission.scene_revision != plan.scene.revision
            or mission.map_revision != grid.revision or mission.robot_instance_id != robot.id
            or robot.profile_id != profile.id or robot.profile_digest != profile_digest
            or mission.start != robot.initial_pose):
        raise ValueError("comparison map/scene/profile/mission identities differ")
    if mission.waypoints:
        raise ValueError("mission waypoints are not supported by this comparison version")
    if (abs(mission.start.position_m[2] - mission.goal.position_m[2]) > EPS
            or any(abs(v) > EPS for p in (mission.start, mission.goal) for v in p.rotation_rpy_deg[:2])):
        raise ValueError("comparison supports planar missions only")
    if type(clearance_m) not in (int, float) or not 0 <= clearance_m <= 1:
        raise ValueError("clearance must be a finite distance in 0..1 metres")
    # Cover chassis, driven wheel extents and passive contacts, not chassis alone.
    radius = max(math.hypot(*profile.chassis_dimensions_m[:2]) / 2,
                 math.hypot(profile.wheel_radius_m, profile.wheel_track_m / 2 + profile.wheel_width_m / 2),
                 *(math.hypot(*wheel.position_xy_m) + wheel.radius_m for wheel in profile.support_wheels))
    body = {"policy_id": POLICY_ID, "site_id": plan.scene.id, "scene_revision": plan.scene.revision,
            "map_revision": grid.revision, "robot_instance_id": robot.id, "profile_digest": profile_digest,
            "mission_revision": mission.revision, "start_xy_m": mission.start.position_m[:2],
            "goal_xy_m": mission.goal.position_m[:2], "footprint_radius_m": radius,
            "clearance_m": float(clearance_m), "inflation_m": radius + clearance_m,
            "max_cell_checks": MAX_CELL_CHECKS}
    return {**body, "revision": canonical_sha256(body)}


@dataclass(frozen=True)
class RouteCandidate:
    id: str
    conditions_revision: str
    points_xy_m: tuple[tuple[float, float], ...]
    provenance: str = "manual"

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id or len(self.id) > 64:
            raise ValueError("route id must contain 1..64 characters")
        if (not isinstance(self.conditions_revision, str) or len(self.conditions_revision) != 64
                or any(c not in "0123456789abcdef" for c in self.conditions_revision)):
            raise ValueError("route must bind comparison conditions")
        if self.provenance not in ("manual", "synthetic", "planner_output"):
            raise ValueError("explicit route provenance required")
        if type(self.points_xy_m) is not tuple or not 2 <= len(self.points_xy_m) <= 128:
            raise ValueError("route requires 2..128 immutable XY points")
        for point in self.points_xy_m:
            if (type(point) is not tuple or len(point) != 2
                    or any(type(v) not in (int, float) or not -100 <= v <= 100 for v in point)):
                raise ValueError("route points must be finite XY metres")
        if any(math.dist(a, b) < EPS for a, b in zip(self.points_xy_m, self.points_xy_m[1:])):
            raise ValueError("consecutive duplicate route points are unsupported")

    @property
    def revision(self):
        return canonical_sha256(asdict(self))


def _intersects(a, b, bounds):
    """Closed segment vs closed AABB using slabs, including touching boundaries."""
    low, high = 0., 1.
    for axis in (0, 1):
        minimum, maximum = bounds[axis], bounds[axis + 2]
        delta = b[axis] - a[axis]
        if abs(delta) < EPS:
            if a[axis] < minimum or a[axis] > maximum:
                return False
        else:
            enter, leave = (minimum - a[axis]) / delta, (maximum - a[axis]) / delta
            if enter > leave:
                enter, leave = leave, enter
            low, high = max(low, enter), min(high, leave)
            if low > high:
                return False
    return True


def _grid_check(route, grid, inflation):
    ox, oy = grid.origin_xy_m
    resolution = grid.resolution_m
    xmax, ymax = ox + grid.width * resolution, oy + grid.height * resolution
    radius = inflation + EPS
    for x, y in route.points_xy_m:
        if not ox + radius < x < xmax - radius or not oy + radius < y < ymax - radius:
            return {"status": "BLOCKED_OR_UNKNOWN", "reason": "footprint_outside_or_touching_grid", "checked_cells": 0}
    checked = 0
    for segment_index, (a, b) in enumerate(zip(route.points_xy_m, route.points_xy_m[1:])):
        x0 = max(0, math.floor((min(a[0], b[0]) - radius - ox) / resolution))
        x1 = min(grid.width - 1, math.floor((max(a[0], b[0]) + radius - ox) / resolution))
        y0 = max(0, math.floor((min(a[1], b[1]) - radius - oy) / resolution))
        y1 = min(grid.height - 1, math.floor((max(a[1], b[1]) + radius - oy) / resolution))
        for row in range(y0, y1 + 1):
            for col in range(x0, x1 + 1):
                checked += 1
                if checked > MAX_CELL_CHECKS:
                    return {"status": "EVALUATION_LIMIT", "reason": "bounded_cell_budget_exceeded", "checked_cells": checked - 1}
                cell = grid.cells[row * grid.width + col]
                if cell == 0:
                    continue
                xmin, ymin = ox + col * resolution, oy + row * resolution
                if _intersects(a, b, (xmin - radius, ymin - radius, xmin + resolution + radius, ymin + resolution + radius)):
                    return {"status": "BLOCKED_OR_UNKNOWN", "reason": "unknown_cell" if cell == -1 else "occupied_cell",
                            "checked_cells": checked, "cell_xy": [col, row], "segment_index": segment_index}
    return {"status": "CLEAR_IN_SUPPLIED_GRID", "reason": "conservative_geometric_check_only", "checked_cells": checked}


def _evaluate(route, conditions, grid):
    if route.conditions_revision != conditions["revision"]:
        raise ValueError("route conditions are stale or different")
    if (math.dist(route.points_xy_m[0], conditions["start_xy_m"]) > EPS
            or math.dist(route.points_xy_m[-1], conditions["goal_xy_m"]) > EPS):
        raise ValueError("both routes must have the exact same mission start and goal")
    vectors = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(route.points_xy_m, route.points_xy_m[1:])]
    headings = [math.atan2(y, x) for x, y in vectors]
    turn = sum(abs(math.atan2(math.sin(b - a), math.cos(b - a))) for a, b in zip(headings, headings[1:]))
    return {"route_id": route.id, "route_revision": route.revision, "provenance": route.provenance,
            "points_xy_m": route.points_xy_m, "length_m": sum(math.hypot(x, y) for x, y in vectors),
            "internal_turn_angle_rad": turn, "grid_check": _grid_check(route, grid, conditions["inflation_m"])}


def compare_routes(plan: SitePlan, profile: RobotProfile, baseline: RouteCandidate,
                   candidate: RouteCandidate, *, clearance_m=.05) -> dict:
    conditions = comparison_conditions(plan, profile, clearance_m=clearance_m)
    if baseline.id == candidate.id:
        raise ValueError("route ids must be distinct")
    before, after = (_evaluate(route, conditions, plan.navigation_map) for route in (baseline, candidate))
    comparable = all(item["grid_check"]["status"] == "CLEAR_IN_SUPPLIED_GRID" for item in (before, after))
    delta = before["length_m"] - after["length_m"] if comparable else None
    winner = None if not comparable else "tie" if abs(delta) <= EPS else candidate.id if delta > 0 else baseline.id
    return {"schema_version": "route-comparison-1.0", "mode": "offline_geometry_only", "conditions": conditions,
            "baseline": before, "candidate": after, "comparable": comparable, "shorter_route_id": winner,
            "candidate_length_reduction_m": delta,
            "candidate_length_reduction_percent": 100 * delta / before["length_m"] if comparable else None,
            "source_verified": False, "execution_authorized": False, "demo_ready": False,
            "physical_validation": "NOT_RUN", "travel_time_improvement": None, "collision_improvement": None,
            "limitations": ["Supplied map and provenance are unverified; geometry is not controller feasibility.",
                            "Unknown/outside cells block comparison; inflated AABBs may reject feasible corner paths.",
                            "No motion, dynamic obstacles, slip, localization error, acceleration or timing simulated.",
                            "This does not generate an optimized route or authorize simulation/physical execution."]}
