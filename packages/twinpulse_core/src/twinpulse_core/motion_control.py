"""Small deterministic motion-control helpers shared by runtime and tests."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RouteCommand:
    """One closed-loop command for the current pose on a straight generated route."""

    linear_mps: float
    angular_rps: float
    distance_m: float
    heading_error_rad: float
    cross_track_error_m: float
    completed: bool
    off_route: bool


def normalize_angle(angle_rad: float) -> float:
    """Wrap an angle to [-pi, pi]."""

    return math.atan2(math.sin(angle_rad), math.cos(angle_rad))


def straight_route_command(
    *,
    position_xy_m: tuple[float, float],
    yaw_rad: float,
    start_xy_m: tuple[float, float],
    goal_xy_m: tuple[float, float],
    position_tolerance_m: float,
    max_linear_speed_mps: float,
    max_angular_speed_rps: float,
    max_cross_track_error_m: float = 0.20,
) -> RouteCommand:
    """Drive toward a goal while correcting heading and guarding aisle departure.

    TwinPulse currently validates generated routes as straight, positive-X paths.  The
    geometry below is nevertheless expressed against the start-to-goal segment so
    the controller's safety metric remains correct if that restriction is relaxed.
    """

    px, py = position_xy_m
    sx, sy = start_xy_m
    gx, gy = goal_xy_m
    dx = gx - px
    dy = gy - py
    distance = math.hypot(dx, dy)
    route_dx = gx - sx
    route_dy = gy - sy
    route_length = math.hypot(route_dx, route_dy)
    if route_length <= 1e-9:
        raise ValueError("route start and goal must be distinct")

    cross_track = abs(route_dx * (py - sy) - route_dy * (px - sx)) / route_length
    desired_heading = math.atan2(dy, dx)
    heading_error = normalize_angle(desired_heading - yaw_rad)
    completed = distance <= position_tolerance_m
    off_route = cross_track > max_cross_track_error_m

    if completed or off_route:
        return RouteCommand(0.0, 0.0, distance, heading_error, cross_track, completed, off_route)

    angular = max(-max_angular_speed_rps, min(max_angular_speed_rps, 2.0 * heading_error))
    # Turn in place for a large heading error.  For small errors, reduce forward
    # speed smoothly so a correction cannot cut across the protected aisle edge.
    heading_scale = max(0.0, math.cos(heading_error))
    linear = min(max_linear_speed_mps, max(0.03, distance * 0.8)) * heading_scale
    return RouteCommand(linear, angular, distance, heading_error, cross_track, False, False)
