"""Strict JSON Schema sent to modern structured-output providers."""

from __future__ import annotations

from typing import Any


def scene_tool_plan_json_schema(*, required_call_slots: bool = False) -> dict[str, Any]:
    """Strict schema for an allowlisted, locally executed scene-tool plan."""

    def number(*, minimum: float, maximum: float, exclusive_minimum: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "number", "maximum": maximum}
        result["exclusiveMinimum" if exclusive_minimum else "minimum"] = minimum
        return result

    def vector(length: int, items: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "array",
            "items": items,
            "minItems": length,
            "maxItems": length,
        }

    coordinate = number(minimum=-20.0, maximum=20.0)
    position2 = vector(2, coordinate)
    position3 = vector(3, coordinate)
    identifier = {
        "type": "string",
        "minLength": 1,
        "maxLength": 64,
        "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$",
    }

    def call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "call_id": identifier,
                "tool": {"type": "string", "const": tool},
                "arguments": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": arguments,
                    "required": list(arguments),
                },
            },
            "required": ["call_id", "tool", "arguments"],
        }

    calls = [
        call(
            "create_floor",
            {
                "id": identifier,
                "center_m": position2,
                "size_m": vector(2, number(minimum=0.0, maximum=20.0, exclusive_minimum=True)),
            },
        ),
        call(
            "create_wall",
            {
                "id": identifier,
                "position_m": position3,
                "dimensions_m": vector(3, number(minimum=0.0, maximum=20.0, exclusive_minimum=True)),
                "yaw_deg": number(minimum=-180.0, maximum=180.0),
            },
        ),
        call(
            "create_rack_row",
            {
                "id": {**identifier, "maxLength": 42},
                "center_m": position2,
                "length_m": number(minimum=0.8, maximum=12.0),
                "depth_m": number(minimum=0.35, maximum=2.5),
                "height_m": number(minimum=0.5, maximum=6.0),
                "bay_count": {"type": "integer", "minimum": 1, "maximum": 8},
                "level_count": {"type": "integer", "minimum": 1, "maximum": 5},
            },
        ),
        call(
            "place_pallet_stack",
            {
                "id": {**identifier, "maxLength": 48},
                "center_m": position2,
                "footprint_m": vector(2, number(minimum=0.0, maximum=2.5, exclusive_minimum=True)),
                "stack_height_m": number(minimum=0.15, maximum=3.0),
                "stack_levels": {"type": "integer", "minimum": 1, "maximum": 4},
            },
        ),
        call(
            "create_aisle_marking",
            {
                "id": identifier,
                "center_m": position2,
                "length_m": number(minimum=0.2, maximum=20.0),
                "width_m": number(minimum=0.01, maximum=1.0),
            },
        ),
        call(
            "place_static_agv",
            {
                "id": {**identifier, "maxLength": 48},
                "center_m": position2,
                "yaw_deg": number(minimum=-180.0, maximum=180.0),
            },
        ),
        call(
            "place_predefined_agv",
            {
                "profile_id": {"type": "string", "const": "agv_compact_2wd_caster_v2"},
                "start_position_m": position3,
            },
        ),
        call(
            "create_navigation_task",
            {
                "id": identifier,
                "goal_position_m": position3,
                "position_tolerance_m": number(minimum=0.01, maximum=0.25),
            },
        ),
    ]
    common_properties: dict[str, Any] = {
        "plan_version": {"type": "string", "const": "1.0"},
        "scene_id": identifier,
        "summary": {"type": "string", "minLength": 1, "maxLength": 500},
        "image_observations": {"type": "string", "maxLength": 1000},
    }
    if required_call_slots:
        by_tool = {item["properties"]["tool"]["const"]: item for item in calls}
        scene_tools = (
            "create_wall", "create_rack_row", "place_pallet_stack",
            "create_aisle_marking", "place_static_agv",
        )
        properties = {
            **common_properties,
            "floor_call": by_tool["create_floor"],
            "scene_calls": {
                "type": "array",
                "items": {"anyOf": [by_tool[name] for name in scene_tools]},
                "maxItems": 20,
            },
            "agv_call": by_tool["place_predefined_agv"],
            "navigation_call": by_tool["create_navigation_task"],
        }
        required = [
            "plan_version", "scene_id", "summary", "image_observations",
            "floor_call", "scene_calls", "agv_call", "navigation_call",
        ]
    else:
        properties = {
            **common_properties,
            "calls": {"type": "array", "items": {"anyOf": calls}, "minItems": 1, "maxItems": 24},
        }
        required = ["plan_version", "scene_id", "summary", "image_observations", "calls"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def spec_bundle_json_schema() -> dict[str, Any]:
    number3 = {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 3,
        "maxItems": 3,
    }
    transform = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"position_m": number3, "rotation_rpy_deg": number3},
        "required": ["position_m", "rotation_rpy_deg"],
    }
    shape = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": ["box"]},
            "dimensions_m": {
                "type": "array",
                "items": {"type": "number", "exclusiveMinimum": 0},
                "minItems": 3,
                "maxItems": 3,
            },
        },
        "required": ["type", "dimensions_m"],
    }
    support_wheel = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "position_xy_m": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
            "radius_m": {"type": "number", "exclusiveMinimum": 0},
            "mass_kg": {"type": "number", "exclusiveMinimum": 0},
            "kind": {"type": "string", "const": "ball_caster"},
        },
        "required": ["id", "position_xy_m", "radius_m", "mass_kg", "kind"],
    }
    scene_object = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "kind": {"type": "string", "enum": ["floor", "wall", "rack", "box"]},
            "transform": transform,
            "shape": shape,
            "collision": {"type": "boolean"},
            "dynamic": {"type": "boolean"},
            "mass_kg": {"type": ["number", "null"]},
            "asset_id": {"type": ["string", "null"]},
        },
        "required": ["id", "kind", "transform", "shape", "collision", "dynamic", "mass_kg", "asset_id"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "scene": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "objects": {"type": "array", "items": scene_object, "minItems": 1, "maxItems": 64},
                    "robot_profile_id": {"type": "string"},
                    "schema_version": {"type": "string", "const": "1.0"},
                    "units": {"type": "string", "const": "m"},
                    "up_axis": {"type": "string", "const": "Z"},
                },
                "required": ["id", "objects", "robot_profile_id", "schema_version", "units", "up_axis"],
            },
            "robot": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "chassis_dimensions_m": number3,
                    "mass_kg": {"type": "number", "exclusiveMinimum": 0},
                    "wheel_radius_m": {"type": "number", "exclusiveMinimum": 0},
                    "wheel_track_m": {"type": "number", "exclusiveMinimum": 0},
                    "wheel_width_m": {"type": "number", "exclusiveMinimum": 0},
                    "max_linear_speed_mps": {"type": "number", "exclusiveMinimum": 0},
                    "max_angular_speed_rps": {"type": "number", "exclusiveMinimum": 0},
                    "support_wheels": {"type": "array", "items": support_wheel, "minItems": 1, "maxItems": 2},
                    "center_of_mass_m": number3,
                    "diagonal_inertia_kg_m2": number3,
                    "max_safe_roll_pitch_deg": {"type": "number", "exclusiveMinimum": 0},
                    "drive_wheel_count": {"type": "integer", "const": 2},
                    "drive_type": {"type": "string", "const": "differential"},
                    "schema_version": {"type": "string", "const": "2.0"},
                },
                "required": [
                    "id", "chassis_dimensions_m", "mass_kg", "wheel_radius_m", "wheel_track_m",
                    "wheel_width_m", "max_linear_speed_mps", "max_angular_speed_rps", "support_wheels",
                    "center_of_mass_m", "diagonal_inertia_kg_m2", "max_safe_roll_pitch_deg",
                    "drive_wheel_count", "drive_type", "schema_version"
                ],
            },
            "task": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "robot_profile_id": {"type": "string"},
                    "start": transform,
                    "goal": transform,
                    "operation": {"type": "string", "const": "navigate"},
                    "position_tolerance_m": {"type": "number", "exclusiveMinimum": 0},
                    "schema_version": {"type": "string", "const": "1.0"},
                },
                "required": [
                    "id", "robot_profile_id", "start", "goal", "operation", "position_tolerance_m",
                    "schema_version"
                ],
            },
            "bundle_version": {"type": "string", "const": "1.0"},
            "allowed_operations": {
                "type": "array", "items": {"type": "string", "const": "navigate"}, "minItems": 1, "maxItems": 1
            },
        },
        "required": ["scene", "robot", "task", "bundle_version", "allowed_operations"],
    }
