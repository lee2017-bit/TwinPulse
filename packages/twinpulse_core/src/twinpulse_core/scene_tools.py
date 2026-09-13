"""Allowlisted scene-tool plans and their deterministic compiler."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Mapping

from .models import RobotProfile, SceneObject, SceneSpec, ShapeSpec, SpecBundle, TaskSpec, Transform
from .robot_profiles import accepted_robot_profile_ids, resolve_robot_profile
from .validation import validate_current_controller_route


_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PLAN_VERSION = "1.0"
_MAX_TOOL_CALLS = 24

SCENE_TOOL_NAMES = frozenset(
    {
        "create_floor",
        "create_wall",
        "create_rack_row",
        "place_pallet_stack",
        "create_aisle_marking",
        "place_static_agv",
        "place_predefined_agv",
        "create_navigation_task",
    }
)

TOOL_DOMAINS = {
    "create_floor": "scene",
    "create_wall": "scene",
    "create_rack_row": "scene",
    "place_pallet_stack": "scene",
    "create_aisle_marking": "scene",
    "place_static_agv": "scene",
    "place_predefined_agv": "robot",
    "create_navigation_task": "task",
}


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


class SceneToolRegistry:
    """Execute validated, deterministic scene operations into a SpecBundle."""

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
            if call.tool == "create_floor":
                objects.append(self._create_floor(args))
            elif call.tool == "create_wall":
                objects.append(self._create_wall(args))
            elif call.tool == "create_rack_row":
                objects.extend(self._create_rack_row(args))
            elif call.tool == "place_pallet_stack":
                objects.extend(self._place_pallet_stack(args))
            elif call.tool == "create_aisle_marking":
                objects.append(self._create_aisle_marking(args))
            elif call.tool == "place_static_agv":
                objects.extend(self._place_static_agv(args))
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
