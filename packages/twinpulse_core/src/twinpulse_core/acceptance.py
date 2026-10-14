# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Deterministic episode metrics shared by headless and interactive runners."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from .models import SpecBundle


@dataclass(frozen=True, slots=True)
class EpisodeSample:
    elapsed_s: float
    position_m: tuple[float, float, float]
    attitude_rpy_rad: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class EpisodeCriteria:
    max_abs_roll_pitch_deg: float
    max_cross_track_error_m: float = 0.08
    max_vertical_range_m: float = 0.04


@dataclass(frozen=True, slots=True)
class EpisodeAssessment:
    passed: bool
    violations: tuple[str, ...]
    sample_count: int
    final_state: str
    goal_error_m: float
    maximum_cross_track_error_m: float
    maximum_abs_roll_deg: float
    maximum_abs_pitch_deg: float
    vertical_range_m: float
    geometric_collision_samples: int
    expected_support_wheels: int
    observed_support_wheels: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_episode(
    bundle: SpecBundle,
    samples: list[EpisodeSample],
    *,
    final_state: str,
    observed_support_wheels: int,
    criteria: EpisodeCriteria | None = None,
) -> EpisodeAssessment:
    if not samples:
        raise ValueError("episode assessment requires at least one sample")
    criteria = criteria or EpisodeCriteria(bundle.robot.max_safe_roll_pitch_deg)
    start = bundle.task.start.position_m
    goal = bundle.task.goal.position_m
    final = samples[-1].position_m
    goal_error = math.hypot(final[0] - goal[0], final[1] - goal[1])
    route_dx = goal[0] - start[0]
    route_dy = goal[1] - start[1]
    route_length = math.hypot(route_dx, route_dy)
    maximum_cross_track = max(
        abs(route_dx * (start[1] - sample.position_m[1]) - (start[0] - sample.position_m[0]) * route_dy)
        / route_length
        for sample in samples
    )
    maximum_roll = max(abs(math.degrees(sample.attitude_rpy_rad[0])) for sample in samples)
    maximum_pitch = max(abs(math.degrees(sample.attitude_rpy_rad[1])) for sample in samples)
    z_values = [sample.position_m[2] for sample in samples]
    vertical_range = max(z_values) - min(z_values)
    collisions = sum(_geometric_collision(bundle, sample) for sample in samples)

    violations: list[str] = []
    if final_state != "completed":
        violations.append(f"runtime did not complete: {final_state}")
    if goal_error > bundle.task.position_tolerance_m:
        violations.append(f"goal error {goal_error:.4f} m exceeds tolerance")
    if maximum_cross_track > criteria.max_cross_track_error_m:
        violations.append(f"cross-track error {maximum_cross_track:.4f} m exceeds limit")
    if maximum_roll > criteria.max_abs_roll_pitch_deg:
        violations.append(f"roll {maximum_roll:.2f} deg exceeds limit")
    if maximum_pitch > criteria.max_abs_roll_pitch_deg:
        violations.append(f"pitch {maximum_pitch:.2f} deg exceeds limit")
    if vertical_range > criteria.max_vertical_range_m:
        violations.append(f"vertical range {vertical_range:.4f} m exceeds limit")
    if collisions:
        violations.append(f"robot footprint overlapped colliders in {collisions} samples")
    expected_supports = len(bundle.robot.support_wheels)
    if observed_support_wheels != expected_supports:
        violations.append(
            f"support wheel prim count {observed_support_wheels} does not match profile {expected_supports}"
        )
    return EpisodeAssessment(
        passed=not violations,
        violations=tuple(violations),
        sample_count=len(samples),
        final_state=final_state,
        goal_error_m=goal_error,
        maximum_cross_track_error_m=maximum_cross_track,
        maximum_abs_roll_deg=maximum_roll,
        maximum_abs_pitch_deg=maximum_pitch,
        vertical_range_m=vertical_range,
        geometric_collision_samples=collisions,
        expected_support_wheels=expected_supports,
        observed_support_wheels=observed_support_wheels,
    )


def _geometric_collision(bundle: SpecBundle, sample: EpisodeSample) -> bool:
    robot_x, robot_y, robot_z = sample.position_m
    roll, pitch, yaw = sample.attitude_rpy_rad
    del roll, pitch
    chassis_x, chassis_y, chassis_z = bundle.robot.chassis_dimensions_m
    robot_half_x = abs(math.cos(yaw)) * chassis_x / 2.0 + abs(math.sin(yaw)) * chassis_y / 2.0
    robot_half_y = abs(math.sin(yaw)) * chassis_x / 2.0 + abs(math.cos(yaw)) * chassis_y / 2.0
    robot_center_z = robot_z + bundle.robot.wheel_radius_m + chassis_z / 2.0
    for item in bundle.scene.objects:
        if item.kind == "floor" or not item.collision or item.shape.type != "box":
            continue
        ox, oy, oz = item.transform.position_m
        dx, dy, dz = item.shape.dimensions_m
        angle = math.radians(item.transform.rotation_rpy_deg[2])
        object_half_x = abs(math.cos(angle)) * dx / 2.0 + abs(math.sin(angle)) * dy / 2.0
        object_half_y = abs(math.sin(angle)) * dx / 2.0 + abs(math.cos(angle)) * dy / 2.0
        overlaps_xy = (
            abs(robot_x - ox) < robot_half_x + object_half_x
            and abs(robot_y - oy) < robot_half_y + object_half_y
        )
        overlaps_z = abs(robot_center_z - oz) < chassis_z / 2.0 + dz / 2.0
        if overlaps_xy and overlaps_z:
            return True
    return False
