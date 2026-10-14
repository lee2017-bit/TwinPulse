# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Strict JSON Schema sent to modern structured-output providers."""

from __future__ import annotations

from typing import Any

from twinpulse_core.tool_catalog import tool_call_schemas


def scene_tool_plan_json_schema(*, required_call_slots: bool = False) -> dict[str, Any]:
    """Strict schema for an allowlisted, locally executed scene-tool plan."""

    calls = tool_call_schemas("1.0")
    identifier = {
        "type": "string",
        "minLength": 1,
        "maxLength": 64,
        "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$",
    }
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


def site_tool_plan_json_schema(plan_version: str = '2.0') -> dict[str, Any]:
    """H3a site proposal: generic static boxes and per-call evidence, locally validated."""

    if plan_version not in {'2.0','2.1','2.2'}:
        raise ValueError('Unsupported site schema version')
    schema = scene_tool_plan_json_schema(required_call_slots=False)
    schema["properties"]["plan_version"] = {"type": "string", "const": plan_version}
    identifier = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$", "maxLength": 64}
    schema["properties"]["calls"]["items"]["anyOf"] = tool_call_schemas(plan_version)
    if plan_version == '2.2':
        schema['properties']['calls']['maxItems'] = 40
    schema["properties"]["call_evidence"] = {
        "type": "array", "minItems": 1, "maxItems": 40 if plan_version == '2.2' else 24,
        "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "call_id": identifier,
                "observation_ids": {"type": "array", "items": identifier, "maxItems": 8},
                "basis": {"type": "string", "enum": ["visual", "user", "inferred", "trusted_measurement"]},
                "note": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "required": ["call_id", "observation_ids", "basis", "note"],
        },
    }
    schema["required"].append("call_evidence")
    return schema


def site_proposal_json_schema(*, photo: bool):
    """Provider wire contract; stored Site2.2 remains unchanged after validation."""
    from copy import deepcopy
    from .scene_contract import PROPOSAL_REVISION
    schema=site_tool_plan_json_schema('2.2')
    calls=schema['properties'].pop('calls')['items']['anyOf']
    by_tool={c['properties']['tool']['const']:c for c in calls}
    evidence=schema['properties']['call_evidence']['items']
    evidence['properties']['user_quote']={'type':['string','null'],'maxLength':256}
    evidence['required'].append('user_quote')
    schema['properties']['call_evidence']['minItems']=0
    schema['properties']['call_evidence']['maxItems']=39
    schema['properties'].update(proposal_version={'const':PROPOSAL_REVISION},
        coordinate_frame={'const':'photo_view_right_rear' if photo else 'local_xy'},
        floor_call=by_tool['create_floor'],floor_evidence=deepcopy(evidence),
        scene_calls=dict(type='array',minItems=0,maxItems=39,
            items={'anyOf':[c for k,c in by_tool.items() if k!='create_floor']}))
    schema['required'].remove('calls')
    schema['required'] += ['proposal_version','coordinate_frame','floor_call','floor_evidence','scene_calls']
    return schema


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
