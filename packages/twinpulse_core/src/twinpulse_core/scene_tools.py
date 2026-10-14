# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Allowlisted scene-tool plans and their deterministic compiler."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import re
from typing import Any, Mapping

from .models import RobotProfile, SceneObject, SceneSpec, ShapeSpec, SpecBundle, TaskSpec, Transform
from .robot_profiles import accepted_robot_profile_ids, resolve_robot_profile
from .tool_catalog import static_tool_definitions, tool_domains, tool_names
from .validation import SpecValidationError, validate_current_controller_route


_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PLAN_VERSION = "1.0"
_MAX_TOOL_CALLS = 24
SCENE_TOOL_CATALOG_REVISION = "scene-tools-1.0"
LOCAL_ROUTE_RESOLVER_REVISION = "straight-x-aabb-v1"

SCENE_TOOL_NAMES = tool_names(_PLAN_VERSION)
TOOL_DOMAINS = tool_domains(_PLAN_VERSION)
_STATIC_TOOL_DEFINITIONS = static_tool_definitions(_PLAN_VERSION)


class SceneToolPlanError(ValueError):
    """Raised when an untrusted tool plan is invalid or unsupported."""


@dataclass(frozen=True, slots=True)
class SceneToolCall:
    call_id: str
    tool: str
    arguments: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "tool": self.tool, "arguments": dict(self.arguments)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SceneToolCall":
        if set(data) != {"call_id", "tool", "arguments"}:
            raise SceneToolPlanError("tool call must contain only call_id, tool, and arguments")
        arguments = data["arguments"]
        if not isinstance(arguments, Mapping):
            raise SceneToolPlanError("tool call arguments must be an object")
        return cls(str(data["call_id"]), str(data["tool"]), dict(arguments))


@dataclass(frozen=True, slots=True)
class SceneToolPlan:
    scene_id: str
    summary: str
    image_observations: str
    calls: tuple[SceneToolCall, ...]
    plan_version: str = _PLAN_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_version": self.plan_version,
            "scene_id": self.scene_id,
            "summary": self.summary,
            "image_observations": self.image_observations,
            "calls": [call.to_dict() for call in self.calls],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SceneToolPlan":
        expected = {"plan_version", "scene_id", "summary", "image_observations", "calls"}
        if set(data) != expected:
            raise SceneToolPlanError("scene tool plan has unexpected or missing fields")
        calls = data["calls"]
        if not isinstance(calls, (list, tuple)):
            raise SceneToolPlanError("scene tool plan calls must be an array")
        return cls(
            scene_id=str(data["scene_id"]),
            summary=str(data["summary"]),
            image_observations=str(data["image_observations"]),
            calls=tuple(SceneToolCall.from_dict(item) for item in calls),
            plan_version=str(data["plan_version"]),
        )


@dataclass(frozen=True, slots=True)
class ToolExecutionReceipt:
    """Auditable result of validating and compiling a high-level tool plan."""

    bundle: SpecBundle
    call_count: int
    expanded_object_count: int
    robot_profile_id: str
    domains: tuple[str, ...]


def scene_tool_plan_to_json(plan: SceneToolPlan, *, indent: int | None = 2) -> str:
    validate_scene_tool_plan(plan)
    return json.dumps(plan.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)


def scene_tool_plan_from_json(payload: str) -> SceneToolPlan:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise SceneToolPlanError("scene tool plan JSON must be an object")
    return validate_scene_tool_plan(SceneToolPlan.from_dict(value))


def validate_scene_tool_plan(plan: SceneToolPlan) -> SceneToolPlan:
    if plan.plan_version != _PLAN_VERSION:
        raise SceneToolPlanError(f"unsupported plan_version: {plan.plan_version}")
    _stable_id(plan.scene_id, "scene_id")
    if not plan.summary.strip() or len(plan.summary) > 500:
        raise SceneToolPlanError("summary must contain 1 to 500 characters")
    if len(plan.image_observations) > 1000:
        raise SceneToolPlanError("image_observations exceeds 1000 characters")
    if not 1 <= len(plan.calls) <= _MAX_TOOL_CALLS:
        raise SceneToolPlanError(f"tool plan must contain 1 to {_MAX_TOOL_CALLS} calls")
    seen: set[str] = set()
    for call in plan.calls:
        _stable_id(call.call_id, "call_id")
        if call.call_id in seen:
            raise SceneToolPlanError(f"duplicate call_id: {call.call_id}")
        seen.add(call.call_id)
        if call.tool not in SCENE_TOOL_NAMES:
            raise SceneToolPlanError(f"tool is not allowlisted: {call.tool}")
    return plan


class _SceneToolRegistryExecutor:
    """Shared execution flow completed by the public registry's tool builders."""

    def execute(self, plan: SceneToolPlan) -> SpecBundle:
        return self.execute_with_receipt(plan).bundle

    def execute_with_receipt(self, plan: SceneToolPlan) -> ToolExecutionReceipt:
        validate_scene_tool_plan(plan)
        objects: list[SceneObject] = []
        robot_calls = [call for call in plan.calls if call.tool == "place_predefined_agv"]
        if len(robot_calls) != 1:
            raise SceneToolPlanError("tool plan must place exactly one predefined AGV")
        requested_profile_id = str(robot_calls[0].arguments.get("profile_id", ""))
        try:
            robot = resolve_robot_profile(requested_profile_id)
        except KeyError as error:
            raise SceneToolPlanError(f"unsupported predefined AGV profile: {requested_profile_id}") from error
        robot_start: tuple[float, float, float] | None = None
        task: TaskSpec | None = None

        for call in plan.calls:
            args = call.arguments
            if call.tool in _STATIC_TOOL_DEFINITIONS:
                objects.extend(self.execute_static_tool(call.tool, args))
            elif call.tool == "place_predefined_agv":
                if robot_start is not None:
                    raise SceneToolPlanError("place_predefined_agv may be called only once")
                robot_start = self._place_predefined_agv(args, robot)
            elif call.tool == "create_navigation_task":
                if task is not None:
                    raise SceneToolPlanError("create_navigation_task may be called only once")
                task = self._create_navigation_task(args, robot)

            if len(objects) > 64:
                raise SceneToolPlanError("expanded scene exceeds the 64-object safety limit")

        if not any(item.kind == "floor" for item in objects):
            raise SceneToolPlanError("tool plan must create a floor")
        if robot_start is None:
            raise SceneToolPlanError("tool plan must place one predefined AGV")
        if task is None:
            raise SceneToolPlanError("tool plan must create one navigation task")
        _validate_rack_row_overlap(plan.calls)
        task = TaskSpec(
            id=task.id,
            robot_profile_id=task.robot_profile_id,
            start=Transform(robot_start),
            goal=task.goal,
            operation=task.operation,
            position_tolerance_m=task.position_tolerance_m,
            schema_version=task.schema_version,
        )
        bundle = SpecBundle(
            scene=SceneSpec(plan.scene_id, tuple(objects), robot.id),
            robot=robot,
            task=task,
        )
        validated = validate_current_controller_route(bundle)
        return ToolExecutionReceipt(
            bundle=validated,
            call_count=len(plan.calls),
            expanded_object_count=len(objects),
            robot_profile_id=robot.id,
            domains=tuple(dict.fromkeys(TOOL_DOMAINS[call.tool] for call in plan.calls)),
        )


def resolve_current_controller_route(plan: SceneToolPlan) -> tuple[SceneToolPlan, bool]:
    """Keep a safe proposed route or deterministically place it in a free horizontal corridor.

    The LLM remains responsible for the observed scene geometry.  Route placement is a
    safety-critical controller concern, so an invalid candidate is replaced locally and the
    returned plan itself carries the final coordinates used to build the bundle.
    """

    validate_scene_tool_plan(plan)
    robots = [call for call in plan.calls if call.tool == "place_predefined_agv"]
    tasks = [call for call in plan.calls if call.tool == "create_navigation_task"]
    floor_projected = False
    if len(robots) == 1 and len(tasks) == 1:
        proposed_start = _vector(robots[0].arguments["start_position_m"], 3, "start_position_m")
        proposed_goal = _vector(tasks[0].arguments["goal_position_m"], 3, "goal_position_m")
        if abs(proposed_start[2]) > 1e-6 or abs(proposed_goal[2]) > 1e-6:
            plan = _project_controller_to_floor(plan)
            floor_projected = True

    registry = SceneToolRegistry()
    try:
        registry.execute(plan)
        return plan, floor_projected
    except SpecValidationError as original_error:
        if not str(original_error).startswith("current controller"):
            raise

    floors = [call for call in plan.calls if call.tool == "create_floor"]
    robots = [call for call in plan.calls if call.tool == "place_predefined_agv"]
    tasks = [call for call in plan.calls if call.tool == "create_navigation_task"]
    if len(floors) != 1 or len(robots) != 1 or len(tasks) != 1:
        raise SceneToolPlanError("local route resolution requires one floor, AGV, and navigation task")

    floor_center = _vector(floors[0].arguments["center_m"], 2, "center_m")
    floor_size = _positive_vector(floors[0].arguments["size_m"], 2, "size_m", maximum=20.0)
    profile = resolve_robot_profile(str(robots[0].arguments.get("profile_id", "")))
    proposed_start = _vector(robots[0].arguments["start_position_m"], 3, "start_position_m")
    proposed_goal = _vector(tasks[0].arguments["goal_position_m"], 3, "goal_position_m")

    margin_x = profile.chassis_dimensions_m[0] / 2.0 + 0.07
    margin_y = profile.chassis_dimensions_m[1] / 2.0 + 0.07
    min_x = floor_center[0] - floor_size[0] / 2.0 + margin_x
    max_x = floor_center[0] + floor_size[0] / 2.0 - margin_x
    min_y = floor_center[1] - floor_size[1] / 2.0 + margin_y
    max_y = floor_center[1] + floor_size[1] / 2.0 - margin_y
    if max_x - min_x <= 0.2 or max_y < min_y:
        raise SceneToolPlanError("no collision-free positive-X route fits inside the floor")

    obstacles = _controller_obstacle_bounds(plan.calls, margin_x=margin_x, margin_y=margin_y)
    y_breaks = {min_y, max_y}
    for _, _, obstacle_min_y, obstacle_max_y in obstacles:
        y_breaks.add(max(min_y, min(max_y, obstacle_min_y)))
        y_breaks.add(max(min_y, min(max_y, obstacle_max_y)))
    ordered_breaks = sorted(y_breaks)
    candidate_y = [
        proposed_start[1],
        floor_center[1],
        *(
            (left + right) / 2.0
            for left, right in zip(ordered_breaks, ordered_breaks[1:])
            if right - left > 0.02
        ),
    ]
    candidate_y = sorted(
        {round(value, 6) for value in candidate_y if min_y <= value <= max_y},
        key=lambda value: (abs(value - proposed_start[1]), abs(value - floor_center[1]), value),
    )

    proposed_length = proposed_goal[0] - proposed_start[0]
    desired_length = min(10.0, max(0.5, proposed_length if proposed_length > 0.2 else 4.0))
    proposed_center_x = (proposed_start[0] + proposed_goal[0]) / 2.0
    candidates: list[tuple[tuple[float, ...], float, float, float]] = []
    for y_value in candidate_y:
        blocked = [
            (left, right)
            for left, right, bottom, top in obstacles
            if bottom <= y_value <= top
        ]
        for gap_min, gap_max in _free_intervals(min_x, max_x, blocked):
            gap_length = gap_max - gap_min
            if gap_length <= 0.2:
                continue
            preserves_x = gap_min <= proposed_start[0] and proposed_goal[0] <= gap_max and proposed_length > 0.2
            route_length = min(10.0, proposed_length) if preserves_x else min(desired_length, gap_length)
            if route_length <= 0.2:
                continue
            if preserves_x:
                start_x, goal_x = proposed_start[0], proposed_goal[0]
            else:
                half = route_length / 2.0
                center_x = min(max(proposed_center_x, gap_min + half), gap_max - half)
                start_x, goal_x = center_x - half, center_x + half
            score = (
                0.0 if preserves_x else 1.0,
                -route_length,
                abs(y_value - proposed_start[1]),
                abs((start_x + goal_x) / 2.0 - proposed_center_x),
                y_value,
                start_x,
            )
            candidates.append((score, start_x, goal_x, y_value))

    for _, start_x, goal_x, y_value in sorted(candidates):
        resolved = _replace_controller_route(plan, start_x=start_x, goal_x=goal_x, y_value=y_value)
        try:
            registry.execute(resolved)
        except SpecValidationError as error:
            if str(error).startswith("current controller"):
                continue
            raise
        return resolved, True
    raise SceneToolPlanError("no collision-free positive-X route fits the generated scene")


def _replace_controller_route(
    plan: SceneToolPlan, *, start_x: float, goal_x: float, y_value: float,
) -> SceneToolPlan:
    calls: list[SceneToolCall] = []
    for call in plan.calls:
        arguments = dict(call.arguments)
        if call.tool == "place_predefined_agv":
            arguments["start_position_m"] = [round(start_x, 6), round(y_value, 6), 0.0]
        elif call.tool == "create_navigation_task":
            arguments["goal_position_m"] = [round(goal_x, 6), round(y_value, 6), 0.0]
        calls.append(replace(call, arguments=arguments))
    return replace(plan, calls=tuple(calls))


def _project_controller_to_floor(plan: SceneToolPlan) -> SceneToolPlan:
    calls: list[SceneToolCall] = []
    for call in plan.calls:
        if call.tool in {"place_predefined_agv", "create_navigation_task"}:
            arguments = dict(call.arguments)
            key = "start_position_m" if call.tool == "place_predefined_agv" else "goal_position_m"
            position = list(arguments[key])
            position[2] = 0.0
            arguments[key] = position
            calls.append(replace(call, arguments=arguments))
        else:
            calls.append(call)
    return replace(plan, calls=tuple(calls))


def _controller_obstacle_bounds(
    calls: tuple[SceneToolCall, ...], *, margin_x: float, margin_y: float,
) -> list[tuple[float, float, float, float]]:
    result: list[tuple[float, float, float, float]] = []
    for call in calls:
        args = call.arguments
        center: tuple[float, float] | None = None
        size: tuple[float, float] | None = None
        yaw = 0.0
        if call.tool == "create_wall":
            position = _vector(args["position_m"], 3, "position_m")
            dimensions = _positive_vector(args["dimensions_m"], 3, "dimensions_m", maximum=20.0)
            if position[2] + dimensions[2] / 2.0 <= 0.0:
                continue
            center, size = (position[0], position[1]), (dimensions[0], dimensions[1])
            yaw = _number(args["yaw_deg"], "yaw_deg", minimum=-180.0, maximum=180.0)
        elif call.tool == "create_rack_row":
            center = _vector(args["center_m"], 2, "center_m")
            size = (
                _number(args["length_m"], "length_m", minimum=0.8, maximum=12.0),
                _number(args["depth_m"], "depth_m", minimum=0.35, maximum=2.5),
            )
        elif call.tool == "place_pallet_stack":
            center = _vector(args["center_m"], 2, "center_m")
            size = _positive_vector(args["footprint_m"], 2, "footprint_m", maximum=2.5)
        elif call.tool == "place_static_agv":
            center = _vector(args["center_m"], 2, "center_m")
            size = (0.72, 0.52)
            yaw = _number(args["yaw_deg"], "yaw_deg", minimum=-180.0, maximum=180.0)
        if center is None or size is None:
            continue
        angle = math.radians(yaw)
        half_x = abs(math.cos(angle)) * size[0] / 2.0 + abs(math.sin(angle)) * size[1] / 2.0
        half_y = abs(math.sin(angle)) * size[0] / 2.0 + abs(math.cos(angle)) * size[1] / 2.0
        result.append((
            center[0] - half_x - margin_x,
            center[0] + half_x + margin_x,
            center[1] - half_y - margin_y,
            center[1] + half_y + margin_y,
        ))
    return result


def _free_intervals(
    minimum: float, maximum: float, blocked: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    clipped = sorted(
        (max(minimum, left), min(maximum, right))
        for left, right in blocked
        if right >= minimum and left <= maximum
    )
    merged: list[list[float]] = []
    for left, right in clipped:
        if not merged or left > merged[-1][1]:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    result: list[tuple[float, float]] = []
    cursor = minimum
    for left, right in merged:
        if left > cursor:
            result.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < maximum:
        result.append((cursor, maximum))
    return result


def _validate_rack_row_overlap(calls: tuple[SceneToolCall, ...]) -> None:
    """Reject rack rows whose physical shelf footprints occupy the same floor area."""

    rows: list[tuple[str, float, float, float, float]] = []
    for call in calls:
        if call.tool != "create_rack_row":
            continue
        args = call.arguments
        center = _vector(args["center_m"], 2, "center_m")
        length = _number(args["length_m"], "length_m", minimum=0.8, maximum=12.0)
        depth = _number(args["depth_m"], "depth_m", minimum=0.35, maximum=2.5)
        bounds = (
            center[0] - length / 2.0,
            center[0] + length / 2.0,
            center[1] - depth / 2.0,
            center[1] + depth / 2.0,
        )
        for other_id, left, right, bottom, top in rows:
            x_overlap = min(bounds[1], right) - max(bounds[0], left)
            y_overlap = min(bounds[3], top) - max(bounds[2], bottom)
            if x_overlap > 1e-3 and y_overlap > 1e-3:
                raise SceneToolPlanError(
                    f"rack rows overlap on the floor: {other_id} and {call.call_id}"
                )
        rows.append((call.call_id, *bounds))


class SceneToolRegistry(_SceneToolRegistryExecutor):
    """Scene-tool registry completed with the deterministic tool builders."""

    def execute_static_tool(self, name: str, args: Mapping[str, Any]) -> list[SceneObject]:
        """Dispatch only catalogued, local static builders with existing validators."""
        definition = _STATIC_TOOL_DEFINITIONS.get(name)
        if definition is None or definition.handler_name is None:
            raise SceneToolPlanError(f"tool is not a local static builder: {name}")
        result = getattr(self, definition.handler_name)(args)
        return result if definition.returns_many else [result]

    @staticmethod
    def _create_floor(args: Mapping[str, Any]) -> SceneObject:
        _exact_keys(args, {"id", "center_m", "size_m"})
        object_id = _object_id(args["id"])
        center = _vector(args["center_m"], 2, "center_m")
        size = _positive_vector(args["size_m"], 2, "size_m", maximum=20.0)
        return SceneObject(
            object_id,
            "floor",
            Transform((center[0], center[1], -0.05)),
            ShapeSpec("box", (size[0], size[1], 0.10)),
        )

    @staticmethod
    def _create_wall(args: Mapping[str, Any]) -> SceneObject:
        _exact_keys(args, {"id", "position_m", "dimensions_m", "yaw_deg"})
        object_id = _object_id(args["id"])
        position = _vector(args["position_m"], 3, "position_m")
        dimensions = _positive_vector(args["dimensions_m"], 3, "dimensions_m", maximum=20.0)
        yaw = _number(args["yaw_deg"], "yaw_deg", minimum=-180.0, maximum=180.0)
        return SceneObject(object_id, "wall", Transform(position, (0.0, 0.0, yaw)), ShapeSpec("box", dimensions))

    @staticmethod
    def _create_rack_row(args: Mapping[str, Any]) -> list[SceneObject]:
        _exact_keys(
            args,
            {"id", "center_m", "length_m", "depth_m", "height_m", "bay_count", "level_count"},
        )
        base_id = _object_id(args["id"], maximum_length=42)
        center = _vector(args["center_m"], 2, "center_m")
        length = _number(args["length_m"], "length_m", minimum=0.8, maximum=12.0)
        depth = _number(args["depth_m"], "depth_m", minimum=0.35, maximum=2.5)
        height = _number(args["height_m"], "height_m", minimum=0.5, maximum=6.0)
        bays = _integer(args["bay_count"], "bay_count", minimum=1, maximum=8)
        levels = _integer(args["level_count"], "level_count", minimum=1, maximum=5)
        upright_width = min(0.10, length / (bays * 5.0))
        result: list[SceneObject] = []
        for index in range(bays + 1):
            x = center[0] - length / 2.0 + length * index / bays
            for side, y in (("a", center[1] - depth / 2.0), ("b", center[1] + depth / 2.0)):
                result.append(
                    SceneObject(
                        f"{base_id}_post_{index}_{side}",
                        "rack",
                        Transform((x, y, height / 2.0)),
                        ShapeSpec("box", (upright_width, upright_width, height)),
                    )
                )
        for level in range(1, levels + 1):
            z = height * level / levels
            result.append(
                SceneObject(
                    f"{base_id}_shelf_{level}",
                    "rack",
                    Transform((center[0], center[1], z)),
                    ShapeSpec("box", (length, depth, 0.08)),
                )
            )
        return result

    @staticmethod
    def _place_pallet_stack(args: Mapping[str, Any]) -> list[SceneObject]:
        _exact_keys(args, {"id", "center_m", "footprint_m", "stack_height_m", "stack_levels"})
        base_id = _object_id(args["id"], maximum_length=48)
        center = _vector(args["center_m"], 2, "center_m")
        footprint = _positive_vector(args["footprint_m"], 2, "footprint_m", maximum=2.5)
        height = _number(args["stack_height_m"], "stack_height_m", minimum=0.15, maximum=3.0)
        levels = _integer(args["stack_levels"], "stack_levels", minimum=1, maximum=4)
        pallet_height = 0.12
        result = [
            SceneObject(
                f"{base_id}_pallet",
                "equipment",
                Transform((center[0], center[1], pallet_height / 2.0)),
                ShapeSpec("box", (footprint[0], footprint[1], pallet_height)),
            )
        ]
        box_height = height / levels
        for level in range(levels):
            result.append(
                SceneObject(
                    f"{base_id}_box_{level + 1}",
                    "box",
                    Transform((center[0], center[1], pallet_height + box_height * (level + 0.5))),
                    ShapeSpec("box", (footprint[0] * 0.92, footprint[1] * 0.92, box_height * 0.92)),
                )
            )
        return result

    @staticmethod
    def _create_aisle_marking(args: Mapping[str, Any]) -> SceneObject:
        _exact_keys(args, {"id", "center_m", "length_m", "width_m"})
        object_id = _object_id(args["id"])
        center = _vector(args["center_m"], 2, "center_m")
        length = _number(args["length_m"], "length_m", minimum=0.2, maximum=20.0)
        width = _number(args["width_m"], "width_m", minimum=0.01, maximum=1.0)
        return SceneObject(
            object_id,
            "equipment",
            Transform((center[0], center[1], 0.006)),
            ShapeSpec("box", (length, width, 0.01)),
            collision=False,
        )

    @staticmethod
    def _place_static_agv(args: Mapping[str, Any]) -> list[SceneObject]:
        """Add a non-driven visual AGV observed in the reference image."""
        _exact_keys(args, {"id", "center_m", "yaw_deg"})
        base_id = _object_id(args["id"], maximum_length=48)
        center = _vector(args["center_m"], 2, "center_m")
        yaw = _number(args["yaw_deg"], "yaw_deg", minimum=-180.0, maximum=180.0)
        return [
            SceneObject(
                f"{base_id}_base",
                "equipment",
                Transform((center[0], center[1], 0.12), (0.0, 0.0, yaw)),
                ShapeSpec("box", (0.72, 0.52, 0.20)),
            ),
            SceneObject(
                f"{base_id}_top",
                "equipment",
                Transform((center[0], center[1], 0.24), (0.0, 0.0, yaw)),
                ShapeSpec("box", (0.46, 0.36, 0.08)),
            ),
        ]

    @staticmethod
    def _place_predefined_agv(args: Mapping[str, Any], robot: RobotProfile) -> tuple[float, float, float]:
        _exact_keys(args, {"profile_id", "start_position_m"})
        if str(args["profile_id"]) not in accepted_robot_profile_ids():
            raise SceneToolPlanError(f"unsupported predefined AGV profile: {args['profile_id']}")
        if resolve_robot_profile(str(args["profile_id"])).id != robot.id:
            raise SceneToolPlanError("predefined AGV profile changed during plan execution")
        start = _vector(args["start_position_m"], 3, "start_position_m")
        if abs(start[2]) > 1e-6:
            raise SceneToolPlanError("AGV start_position_m must be on z=0")
        return start

    @staticmethod
    def _create_navigation_task(args: Mapping[str, Any], robot: RobotProfile) -> TaskSpec:
        _exact_keys(args, {"id", "goal_position_m", "position_tolerance_m"})
        task_id = _object_id(args["id"])
        goal = _vector(args["goal_position_m"], 3, "goal_position_m")
        tolerance = _number(
            args["position_tolerance_m"], "position_tolerance_m", minimum=0.01, maximum=0.25
        )
        return TaskSpec(task_id, robot.id, Transform((0.0, 0.0, 0.0)), Transform(goal), position_tolerance_m=tolerance)


def demo_warehouse_tool_plan() -> SceneToolPlan:
    """Explicit M1-style demo plan used only by tests and the mock provider."""
    return SceneToolPlan(
        scene_id="warehouse_tool_demo_v1",
        summary="Deterministic demo warehouse with two rack rows and a center route.",
        image_observations="Mock provider; no image interpretation performed.",
        calls=(
            SceneToolCall("floor", "create_floor", {"id": "floor_main", "center_m": [0.0, 0.0], "size_m": [8.0, 6.0]}),
            SceneToolCall(
                "rack_left",
                "create_rack_row",
                {"id": "rack_left", "center_m": [1.5, 1.6], "length_m": 2.0, "depth_m": 0.6, "height_m": 1.5, "bay_count": 2, "level_count": 2},
            ),
            SceneToolCall(
                "rack_right",
                "create_rack_row",
                {"id": "rack_right", "center_m": [1.5, -1.6], "length_m": 2.0, "depth_m": 0.6, "height_m": 1.5, "bay_count": 2, "level_count": 2},
            ),
            SceneToolCall(
                "agv", "place_predefined_agv", {"profile_id": "agv_compact_2wd_caster_v2", "start_position_m": [0.0, 0.0, 0.0]}
            ),
            SceneToolCall(
                "task", "create_navigation_task", {"id": "demo_route_v1", "goal_position_m": [1.5, 0.0, 0.0], "position_tolerance_m": 0.05}
            ),
        ),
    )
def _exact_keys(arguments: Mapping[str, Any], expected: set[str]) -> None:
    actual = set(arguments)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SceneToolPlanError(f"tool arguments mismatch; missing={missing}, extra={extra}")


def _stable_id(value: object, name: str, *, maximum_length: int = 64) -> str:
    text = str(value)
    if len(text) > maximum_length or not _ID_PATTERN.fullmatch(text):
        raise SceneToolPlanError(f"{name} is not a stable identifier: {text!r}")
    return text


def _object_id(value: object, *, maximum_length: int = 64) -> str:
    return _stable_id(value, "object id", maximum_length=maximum_length)


def _number(value: object, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SceneToolPlanError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise SceneToolPlanError(f"{name} must be within {minimum:g}..{maximum:g}")
    return number


def _integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise SceneToolPlanError(f"{name} must be an integer within {minimum}..{maximum}")
    return value


def _vector(value: object, length: int, name: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise SceneToolPlanError(f"{name} must contain exactly {length} numbers")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise SceneToolPlanError(f"{name} must contain only numbers")
        number = float(item)
        if not math.isfinite(number) or abs(number) > 20.0:
            raise SceneToolPlanError(f"{name} must stay within the 20 m prototype bounds")
        result.append(number)
    return tuple(result)


def _positive_vector(value: object, length: int, name: str, *, maximum: float) -> tuple[float, ...]:
    result = _vector(value, length, name)
    if any(item <= 0.0 or item > maximum for item in result):
        raise SceneToolPlanError(f"{name} must contain positive values no larger than {maximum:g}")
    return result
