"""Validation boundary between untrusted inputs and Isaac scene mutation."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from .models import RobotProfile, SceneObject, SpecBundle, TaskSpec, Transform


_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_SHAPE_DIMENSIONS = {"box": 3, "cylinder": 2}
_OBJECT_KINDS = {"floor", "wall", "rack", "box", "equipment"}
_DRIVE_TYPES = {"differential"}
_SUPPORTED_VERSION = "1.0"
_SUPPORTED_ROBOT_VERSION = "2.0"
_SUPPORT_WHEEL_KINDS = {"ball_caster"}


class SpecValidationError(ValueError):
    """Raised when a specification is unsafe or unsupported."""


@dataclass(frozen=True, slots=True)
class ValidationLimits:
    max_objects: int = 64
    max_dimension_m: float = 50.0
    max_abs_position_m: float = 100.0
    max_mass_kg: float = 10_000.0
    allowed_asset_ids: frozenset[str] = frozenset()
    allowed_operations: frozenset[str] = frozenset({"navigate"})


def _fail(message: str) -> None:
    raise SpecValidationError(message)


def _finite(values: tuple[float, ...], name: str) -> None:
    if not all(math.isfinite(value) for value in values):
        _fail(f"{name} must contain only finite numbers")


def _id(value: str, name: str) -> None:
    if not _ID_PATTERN.fullmatch(value):
        _fail(f"{name} is not a stable identifier: {value!r}")


def _transform(transform: Transform, name: str, limits: ValidationLimits) -> None:
    _finite(transform.position_m, f"{name}.position_m")
    _finite(transform.rotation_rpy_deg, f"{name}.rotation_rpy_deg")
    if any(abs(value) > limits.max_abs_position_m for value in transform.position_m):
        _fail(f"{name}.position_m exceeds configured scene bounds")


def _scene_object(item: SceneObject, limits: ValidationLimits) -> None:
    _id(item.id, "scene object id")
    if item.kind not in _OBJECT_KINDS:
        _fail(f"unsupported scene object kind: {item.kind}")
    _transform(item.transform, item.id, limits)
    expected_dimensions = _SHAPE_DIMENSIONS.get(item.shape.type)
    if expected_dimensions is None:
        _fail(f"unsupported shape type: {item.shape.type}")
    if len(item.shape.dimensions_m) != expected_dimensions:
        _fail(f"{item.id} {item.shape.type} requires {expected_dimensions} dimensions")
    _finite(item.shape.dimensions_m, f"{item.id}.dimensions_m")
    if any(value <= 0.0 or value > limits.max_dimension_m for value in item.shape.dimensions_m):
        _fail(f"{item.id}.dimensions_m must be positive and within configured limits")
    if item.dynamic:
        if item.mass_kg is None or not math.isfinite(item.mass_kg) or not 0.0 < item.mass_kg <= limits.max_mass_kg:
            _fail(f"dynamic object {item.id} requires a valid positive mass_kg")
    elif item.mass_kg is not None:
        _fail(f"static object {item.id} must not define mass_kg")
    if item.asset_id is not None and item.asset_id not in limits.allowed_asset_ids:
        _fail(f"asset_id is not allowlisted: {item.asset_id}")


def _robot(robot: RobotProfile, limits: ValidationLimits) -> None:
    _id(robot.id, "robot id")
    if robot.schema_version != _SUPPORTED_ROBOT_VERSION:
        _fail(f"unsupported robot schema_version: {robot.schema_version}")
    if robot.drive_type not in _DRIVE_TYPES:
        _fail(f"unsupported drive_type: {robot.drive_type}")
    positive_values = (
        *robot.chassis_dimensions_m,
        robot.mass_kg,
        robot.wheel_radius_m,
        robot.wheel_track_m,
        robot.wheel_width_m,
        robot.max_linear_speed_mps,
        robot.max_angular_speed_rps,
        *robot.diagonal_inertia_kg_m2,
        robot.max_safe_roll_pitch_deg,
    )
    _finite((*positive_values, *robot.center_of_mass_m), "robot numeric fields")
    if any(value <= 0.0 for value in positive_values):
        _fail("robot dimensions, mass, wheel geometry, and speed limits must be positive")
    if any(value > limits.max_dimension_m for value in robot.chassis_dimensions_m):
        _fail("robot chassis exceeds configured dimensions")
    if robot.mass_kg > limits.max_mass_kg:
        _fail("robot mass exceeds configured limit")
    if robot.drive_wheel_count != 2:
        _fail("differential profile requires exactly two driven wheels")
    if not 1 <= len(robot.support_wheels) <= 2:
        _fail("differential profile requires one or two passive support wheels")
    support_ids = [support.id for support in robot.support_wheels]
    if len(support_ids) != len(set(support_ids)):
        _fail("support wheel ids must be unique")
    chassis_half_x = robot.chassis_dimensions_m[0] / 2.0
    chassis_half_y = robot.chassis_dimensions_m[1] / 2.0
    for support in robot.support_wheels:
        _id(support.id, "support wheel id")
        if support.kind not in _SUPPORT_WHEEL_KINDS:
            _fail(f"unsupported support wheel kind: {support.kind}")
        _finite((*support.position_xy_m, support.radius_m, support.mass_kg), support.id)
        if support.radius_m <= 0.0 or support.mass_kg <= 0.0:
            _fail("support wheel radius and mass must be positive")
        if abs(support.position_xy_m[0]) > chassis_half_x or abs(support.position_xy_m[1]) > chassis_half_y:
            _fail(f"support wheel {support.id} lies outside the chassis footprint")
    for value, half_extent in zip(robot.center_of_mass_m, (chassis_half_x, chassis_half_y, robot.chassis_dimensions_m[2] / 2.0), strict=True):
        if abs(value) > half_extent:
            _fail("robot center_of_mass_m must remain inside the chassis")


def _task(task: TaskSpec, robot: RobotProfile, limits: ValidationLimits) -> None:
    _id(task.id, "task id")
    if task.schema_version != _SUPPORTED_VERSION:
        _fail(f"unsupported task schema_version: {task.schema_version}")
    if task.robot_profile_id != robot.id:
        _fail("task references an unknown robot profile")
    if task.operation not in limits.allowed_operations:
        _fail(f"operation is not allowlisted: {task.operation}")
    _transform(task.start, "task.start", limits)
    _transform(task.goal, "task.goal", limits)
    if not math.isfinite(task.position_tolerance_m) or task.position_tolerance_m <= 0.0:
        _fail("position_tolerance_m must be finite and positive")


def validate_bundle(bundle: SpecBundle, limits: ValidationLimits | None = None) -> SpecBundle:
    """Validate the complete cross-referenced bundle and return it unchanged."""

    limits = limits or ValidationLimits()
    if bundle.bundle_version != _SUPPORTED_VERSION:
        _fail(f"unsupported bundle_version: {bundle.bundle_version}")
    scene = bundle.scene
    _id(scene.id, "scene id")
    if scene.schema_version != _SUPPORTED_VERSION:
        _fail(f"unsupported scene schema_version: {scene.schema_version}")
    if scene.units != "m" or scene.up_axis != "Z":
        _fail("only SI meters with Z-up are supported")
    if len(scene.objects) > limits.max_objects:
        _fail(f"scene object count exceeds configured limit of {limits.max_objects}")
    object_ids = [item.id for item in scene.objects]
    if len(object_ids) != len(set(object_ids)):
        _fail("scene object ids must be unique")
    for item in scene.objects:
        _scene_object(item, limits)
    _robot(bundle.robot, limits)
    if scene.robot_profile_id != bundle.robot.id:
        _fail("scene references an unknown robot profile")
    if set(bundle.allowed_operations) - limits.allowed_operations:
        _fail("bundle declares an operation outside configured allowlist")
    if bundle.task.operation not in bundle.allowed_operations:
        _fail("task operation is not declared by the bundle")
    _task(bundle.task, bundle.robot, limits)
    return bundle


def validate_current_controller_route(bundle: SpecBundle) -> SpecBundle:
    """Validate the deliberately narrow straight-line route supported before Nav2."""
    validate_bundle(bundle)
    start = bundle.task.start
    goal = bundle.task.goal
    sx, sy, sz = start.position_m
    gx, gy, gz = goal.position_m
    if any(abs(value) > 1e-6 for value in start.rotation_rpy_deg):
        _fail("current controller requires an unrotated robot start pose")
    if abs(sz) > 1e-6 or abs(gz) > 1e-6 or abs(gy - sy) > 1e-3 or gx <= sx + 0.2:
        _fail("current controller requires a positive-X straight route on the floor")
    if gx - sx > 10.0:
        _fail("current controller route exceeds the 10 m prototype limit")

    floors = [item for item in bundle.scene.objects if item.kind == "floor" and item.shape.type == "box"]
    route_on_floor = False
    for floor in floors:
        if any(abs(value) > 1e-6 for value in floor.transform.rotation_rpy_deg):
            continue
        fx, fy, _ = floor.transform.position_m
        dx, dy, _ = floor.shape.dimensions_m
        if fx - dx / 2 <= sx <= gx <= fx + dx / 2 and fy - dy / 2 <= sy <= fy + dy / 2:
            route_on_floor = True
            break
    if not route_on_floor:
        _fail("current controller route must stay inside an axis-aligned floor")

    robot_half_x = bundle.robot.chassis_dimensions_m[0] / 2 + 0.05
    robot_half_y = bundle.robot.chassis_dimensions_m[1] / 2 + 0.05
    corridor_min_x = sx - robot_half_x
    corridor_max_x = gx + robot_half_x
    for item in bundle.scene.objects:
        if item.kind == "floor" or not item.collision or item.shape.type != "box":
            continue
        roll, pitch, yaw = item.transform.rotation_rpy_deg
        if abs(roll) > 1e-6 or abs(pitch) > 1e-6:
            _fail(f"current controller does not support tilted collider {item.id}")
        ox, oy, oz = item.transform.position_m
        dx, dy, dz = item.shape.dimensions_m
        if oz + dz / 2 <= 0.0:
            continue
        angle = math.radians(yaw)
        half_x = abs(math.cos(angle)) * dx / 2 + abs(math.sin(angle)) * dy / 2
        half_y = abs(math.sin(angle)) * dx / 2 + abs(math.cos(angle)) * dy / 2
        overlaps_x = ox + half_x >= corridor_min_x and ox - half_x <= corridor_max_x
        overlaps_y = abs(oy - sy) <= half_y + robot_half_y
        if overlaps_x and overlaps_y:
            _fail(f"current controller route is blocked by {item.id}")
    return bundle
