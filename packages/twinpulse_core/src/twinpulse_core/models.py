# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Immutable TwinPulse M1 data contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


def _tuple3(value: object, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly three numbers")
    return tuple(float(item) for item in value)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class Transform:
    position_m: tuple[float, float, float]
    rotation_rpy_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Transform":
        return cls(
            position_m=_tuple3(data["position_m"], "position_m"),
            rotation_rpy_deg=_tuple3(data.get("rotation_rpy_deg", (0.0, 0.0, 0.0)), "rotation_rpy_deg"),
        )


@dataclass(frozen=True, slots=True)
class ShapeSpec:
    type: str
    dimensions_m: tuple[float, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ShapeSpec":
        values = data["dimensions_m"]
        if not isinstance(values, (list, tuple)):
            raise ValueError("dimensions_m must be a list or tuple")
        return cls(type=str(data["type"]), dimensions_m=tuple(float(item) for item in values))


@dataclass(frozen=True, slots=True)
class SceneObject:
    id: str
    kind: str
    transform: Transform
    shape: ShapeSpec
    collision: bool = True
    dynamic: bool = False
    mass_kg: float | None = None
    asset_id: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SceneObject":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            transform=Transform.from_dict(data["transform"]),
            shape=ShapeSpec.from_dict(data["shape"]),
            collision=bool(data.get("collision", True)),
            dynamic=bool(data.get("dynamic", False)),
            mass_kg=None if data.get("mass_kg") is None else float(data["mass_kg"]),
            asset_id=None if data.get("asset_id") is None else str(data["asset_id"]),
        )


@dataclass(frozen=True, slots=True)
class SceneSpec:
    id: str
    objects: tuple[SceneObject, ...]
    robot_profile_id: str
    schema_version: str = "1.0"
    units: str = "m"
    up_axis: str = "Z"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SceneSpec":
        return cls(
            id=str(data["id"]),
            objects=tuple(SceneObject.from_dict(item) for item in data["objects"]),
            robot_profile_id=str(data["robot_profile_id"]),
            schema_version=str(data.get("schema_version", "1.0")),
            units=str(data.get("units", "m")),
            up_axis=str(data.get("up_axis", "Z")),
        )


@dataclass(frozen=True, slots=True)
class SupportWheelSpec:
    """Passive support contact owned by a vetted robot profile."""

    id: str
    position_xy_m: tuple[float, float]
    radius_m: float
    mass_kg: float
    kind: str = "ball_caster"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SupportWheelSpec":
        position = data["position_xy_m"]
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise ValueError("position_xy_m must contain exactly two numbers")
        return cls(
            id=str(data["id"]),
            position_xy_m=(float(position[0]), float(position[1])),
            radius_m=float(data["radius_m"]),
            mass_kg=float(data["mass_kg"]),
            kind=str(data.get("kind", "ball_caster")),
        )


def _legacy_support_wheels(chassis_dimensions_m: tuple[float, float, float]) -> tuple[SupportWheelSpec, ...]:
    """Upgrade schema-1 profiles to the safe two-drive/two-support contract."""

    offset_x = chassis_dimensions_m[0] * 0.40
    return (
        SupportWheelSpec("front_caster", (offset_x, 0.0), 0.04, 0.25),
        SupportWheelSpec("rear_caster", (-offset_x, 0.0), 0.04, 0.25),
    )


@dataclass(frozen=True, slots=True)
class RobotProfile:
    id: str
    chassis_dimensions_m: tuple[float, float, float]
    mass_kg: float
    wheel_radius_m: float
    wheel_track_m: float
    wheel_width_m: float
    max_linear_speed_mps: float
    max_angular_speed_rps: float
    support_wheels: tuple[SupportWheelSpec, ...]
    center_of_mass_m: tuple[float, float, float]
    diagonal_inertia_kg_m2: tuple[float, float, float]
    max_safe_roll_pitch_deg: float = 8.0
    drive_wheel_count: int = 2
    drive_type: str = "differential"
    schema_version: str = "2.0"

    @property
    def wheel_base_m(self) -> float:
        """Compatibility alias for the old, incorrectly named track-width field."""

        return self.wheel_track_m

    @property
    def contact_count(self) -> int:
        return self.drive_wheel_count + len(self.support_wheels)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RobotProfile":
        dimensions = _tuple3(data["chassis_dimensions_m"], "chassis_dimensions_m")
        legacy = str(data.get("schema_version", "1.0")) == "1.0"
        support_data = data.get("support_wheels")
        if support_data is None and legacy:
            support_wheels = _legacy_support_wheels(dimensions)
        elif isinstance(support_data, (list, tuple)):
            support_wheels = tuple(SupportWheelSpec.from_dict(item) for item in support_data)
        else:
            raise ValueError("support_wheels must be an array")
        inertia = data.get("diagonal_inertia_kg_m2", (0.1667, 0.3333, 0.4333))
        return cls(
            id=str(data["id"]),
            chassis_dimensions_m=dimensions,
            mass_kg=float(data["mass_kg"]),
            wheel_radius_m=float(data["wheel_radius_m"]),
            wheel_track_m=float(data.get("wheel_track_m", data.get("wheel_base_m"))),
            wheel_width_m=float(data["wheel_width_m"]),
            max_linear_speed_mps=float(data["max_linear_speed_mps"]),
            max_angular_speed_rps=float(data["max_angular_speed_rps"]),
            support_wheels=support_wheels,
            center_of_mass_m=_tuple3(data.get("center_of_mass_m", (0.0, 0.0, -0.03)), "center_of_mass_m"),
            diagonal_inertia_kg_m2=_tuple3(inertia, "diagonal_inertia_kg_m2"),
            max_safe_roll_pitch_deg=float(data.get("max_safe_roll_pitch_deg", 8.0)),
            drive_wheel_count=int(data.get("drive_wheel_count", 2)),
            drive_type=str(data.get("drive_type", "differential")),
            schema_version="2.0" if legacy else str(data.get("schema_version", "2.0")),
        )


@dataclass(frozen=True, slots=True)
class TaskSpec:
    id: str
    robot_profile_id: str
    start: Transform
    goal: Transform
    operation: str = "navigate"
    position_tolerance_m: float = 0.025
    schema_version: str = "1.0"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskSpec":
        return cls(
            id=str(data["id"]),
            robot_profile_id=str(data["robot_profile_id"]),
            start=Transform.from_dict(data["start"]),
            goal=Transform.from_dict(data["goal"]),
            operation=str(data.get("operation", "navigate")),
            position_tolerance_m=float(data.get("position_tolerance_m", 0.025)),
            schema_version=str(data.get("schema_version", "1.0")),
        )


@dataclass(frozen=True, slots=True)
class SpecBundle:
    scene: SceneSpec
    robot: RobotProfile
    task: TaskSpec
    bundle_version: str = "1.0"
    allowed_operations: tuple[str, ...] = field(default=("navigate",))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SpecBundle":
        operations = data.get("allowed_operations", ("navigate",))
        if not isinstance(operations, (list, tuple)):
            raise ValueError("allowed_operations must be a list or tuple")
        return cls(
            scene=SceneSpec.from_dict(data["scene"]),
            robot=RobotProfile.from_dict(data["robot"]),
            task=TaskSpec.from_dict(data["task"]),
            bundle_version=str(data.get("bundle_version", "1.0")),
            allowed_operations=tuple(str(item) for item in operations),
        )
