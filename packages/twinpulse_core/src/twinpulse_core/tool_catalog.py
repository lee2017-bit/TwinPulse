# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Versioned, local-only definitions for allowlisted scene planning tools.

This is metadata for proposal validation and existing deterministic executors,
not a provider-controlled command registry.  Keep old schema shapes stable.
"""

from __future__ import annotations

from dataclasses import dataclass,replace
from typing import Any
from .room_item_catalog import ROOM_ITEM_KINDS
from .model_library import FURNITURE_MODELS, FINISHES, PARAMETRIC_FURNITURE_VERSION


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    domain: str
    versions: tuple[str, ...]
    call_schema: dict[str, Any]
    handler_name: str | None = None
    returns_many: bool = False


def _number(*, minimum: float, maximum: float, exclusive_minimum: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "number", "maximum": maximum}
    result["exclusiveMinimum" if exclusive_minimum else "minimum"] = minimum
    return result


def _vector(length: int, items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items, "minItems": length, "maxItems": length}


def _call(tool: str, arguments: dict[str, Any], identifier: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "call_id": identifier,
            "tool": {"type": "string", "const": tool},
            "arguments": {
                "type": "object", "additionalProperties": False,
                "properties": arguments, "required": list(arguments),
            },
        },
        "required": ["call_id", "tool", "arguments"],
    }


def _site_box_call() -> dict[str, Any]:
    # Historical v2 schema intentionally differs from v1 (e.g. no minLength).
    identifier = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$", "maxLength": 64}
    coordinate = {"type": "number", "minimum": -20, "maximum": 20}
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "call_id": identifier, "tool": {"type": "string", "const": "create_box_obstacle"},
            "arguments": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "id": identifier,
                    "center_m": {"type": "array", "items": coordinate, "minItems": 2, "maxItems": 2},
                    "dimensions_m": {"type": "array", "items": {"type": "number", "exclusiveMinimum": 0,
                                                                "maximum": 20}, "minItems": 3, "maxItems": 3},
                    "yaw_deg": {"type": "number", "minimum": -180, "maximum": 180},
                },
                "required": ["id", "center_m", "dimensions_m", "yaw_deg"],
            },
        },
        "required": ["call_id", "tool", "arguments"],
    }


def furniture_call_schema(parametric: bool = False) -> dict[str, Any]:
    """Keep the historical argument branch exact; new catalog is explicit opt-in."""
    identifier = {'type':'string','minLength':1,'maxLength':64,'pattern':'^[A-Za-z][A-Za-z0-9_-]{0,63}$'}
    fields = dict(id={**identifier,'maxLength':48}, kind={'type':'string','enum':list(FURNITURE_MODELS)},
        catalog_version={'type':'string','const':'furniture-blocks-1.0'},
        center_m=_vector(2,_number(minimum=-20.,maximum=20.)),
        yaw_deg=_number(minimum=-180.,maximum=180.))
    call = _call('place_furniture',fields,identifier)
    if parametric:
        old = call['properties']['arguments']
        branches = [old]
        for kind, (_,lower,upper,variants,_) in FURNITURE_MODELS.items():
            args = {**fields,'kind':{'type':'string','const':kind},
                'catalog_version':{'type':'string','const':PARAMETRIC_FURNITURE_VERSION},
                # Per-axis limits are enforced by the local executor/manifest.
                # Homogeneous items keep this schema compatible with providers.
                'dimensions_m':_vector(3,_number(minimum=min(lower),maximum=max(upper))),
                'variant':{'type':'string','enum':list(variants)},
                'finish':{'type':'string','enum':list(FINISHES)}}
            branches.append(_call('place_furniture',args,identifier)['properties']['arguments'])
        call['properties']['arguments'] = {'anyOf':branches}
    return call


def tool_definitions() -> tuple[ToolDefinition, ...]:
    """Return fresh schemas in stable provider order; callers may mutate their copy."""
    from .model_recipe import recipe_schema, SUPPORTED_INTERPRETERS, KINDS as RECIPE_KINDS
    coordinate = _number(minimum=-20.0, maximum=20.0)
    position2 = _vector(2, coordinate)
    position3 = _vector(3, coordinate)
    identifier = {
        "type": "string", "minLength": 1, "maxLength": 64,
        "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$",
    }
    both = ("1.0", "2.0", "2.1", "2.2")
    definitions = (
        ToolDefinition("create_floor", "scene", both, _call("create_floor", {
            "id": identifier, "center_m": position2,
            "size_m": _vector(2, _number(minimum=0.0, maximum=20.0, exclusive_minimum=True)),
        }, identifier), "_create_floor"),
        ToolDefinition("create_wall", "scene", both, _call("create_wall", {
            "id": identifier, "position_m": position3,
            "dimensions_m": _vector(3, _number(minimum=0.0, maximum=20.0, exclusive_minimum=True)),
            "yaw_deg": _number(minimum=-180.0, maximum=180.0),
        }, identifier), "_create_wall"),
        ToolDefinition("create_rack_row", "scene", both, _call("create_rack_row", {
            "id": {**identifier, "maxLength": 42}, "center_m": position2,
            "length_m": _number(minimum=0.8, maximum=12.0),
            "depth_m": _number(minimum=0.35, maximum=2.5),
            "height_m": _number(minimum=0.5, maximum=6.0),
            "bay_count": {"type": "integer", "minimum": 1, "maximum": 8},
            "level_count": {"type": "integer", "minimum": 1, "maximum": 5},
        }, identifier), "_create_rack_row", True),
        ToolDefinition("place_pallet_stack", "scene", both, _call("place_pallet_stack", {
            "id": {**identifier, "maxLength": 48}, "center_m": position2,
            "footprint_m": _vector(2, _number(minimum=0.0, maximum=2.5, exclusive_minimum=True)),
            "stack_height_m": _number(minimum=0.15, maximum=3.0),
            "stack_levels": {"type": "integer", "minimum": 1, "maximum": 4},
        }, identifier), "_place_pallet_stack", True),
        ToolDefinition("create_aisle_marking", "scene", both, _call("create_aisle_marking", {
            "id": identifier, "center_m": position2,
            "length_m": _number(minimum=0.2, maximum=20.0),
            "width_m": _number(minimum=0.01, maximum=1.0),
        }, identifier), "_create_aisle_marking"),
        ToolDefinition("place_static_agv", "scene", both, _call("place_static_agv", {
            "id": {**identifier, "maxLength": 48}, "center_m": position2,
            "yaw_deg": _number(minimum=-180.0, maximum=180.0),
        }, identifier), "_place_static_agv", True),
        ToolDefinition("place_predefined_agv", "robot", both, _call("place_predefined_agv", {
            "profile_id": {"type": "string", "const": "agv_compact_2wd_caster_v2"},
            "start_position_m": position3,
        }, identifier)),
        ToolDefinition("create_navigation_task", "task", both, _call("create_navigation_task", {
            "id": identifier, "goal_position_m": position3,
            "position_tolerance_m": _number(minimum=0.01, maximum=0.25),
        }, identifier)),
        ToolDefinition("create_box_obstacle", "scene", ("2.0", "2.1", "2.2"), _site_box_call()),
        ToolDefinition('place_furniture','scene',('2.1',),furniture_call_schema(),returns_many=True),
        ToolDefinition('place_furniture','scene',('2.2',),furniture_call_schema(True),returns_many=True),
        ToolDefinition('place_model_recipe','scene',('2.2',),_call('place_model_recipe', {
            'id': {**identifier,'maxLength':32}, 'kind': {'enum':list(RECIPE_KINDS)},
            'model_id': {'type':'string','pattern':r'^local\.[0-9a-f]{24}$'},
            'recipe_sha256': {'type':'string','pattern':r'^[0-9a-f]{64}$'},
            'interpreter_version': {'enum':list(SUPPORTED_INTERPRETERS)}, 'recipe':recipe_schema(include_legacy=True),
            'parameters': {'type':'object','additionalProperties':{'type':'number'}},
            'center_m':position2,'yaw_deg':_number(minimum=-180.,maximum=180.),
        },identifier),returns_many=True),
        ToolDefinition('place_room_item', 'scene', ('2.2',), _call('place_room_item', {
            'id': {**identifier, 'maxLength': 42},
            'kind': {'type': 'string', 'enum': list(ROOM_ITEM_KINDS)},
            'label': {'type': 'string', 'minLength': 1, 'maxLength': 120},
            'catalog_version': {'type': 'string', 'enum': ['room-items-1.0','room-items-1.1','room-items-1.2','room-items-1.3']},
            'position_m': position3,
            'dimensions_m': _vector(3, _number(minimum=0., maximum=10., exclusive_minimum=True)),
            'yaw_deg': _number(minimum=-180., maximum=180.),
            'observation_time_utc': {'type': ['string', 'null'], 'maxLength': 40},
        }, identifier), returns_many=True),
    )
    # Host-only 2.3. Provider generation retains its unchanged 2.2 schema.
    inherited=tuple(replace(d,versions=(*d.versions,'2.3')) if '2.2' in d.versions else d for d in definitions)
    return (*inherited,ToolDefinition('place_library_asset','scene',('2.3',),
        _call('place_library_asset',dict(id={**identifier,'maxLength':42},snapshot={'type':'object'},
            position_m=position3,yaw_deg=_number(minimum=-180.,maximum=180.)),identifier)))


def tool_names(plan_version: str) -> frozenset[str]:
    return frozenset(item.name for item in tool_definitions() if plan_version in item.versions)


def tool_domains(plan_version: str) -> dict[str, str]:
    return {item.name: item.domain for item in tool_definitions() if plan_version in item.versions}


def tool_call_schemas(plan_version: str) -> list[dict[str, Any]]:
    return [item.call_schema for item in tool_definitions() if plan_version in item.versions]


def static_tool_definitions(plan_version: str) -> dict[str, ToolDefinition]:
    """Only trusted local static handlers; robot/task and v2 box stay in their owners."""
    return {item.name: item for item in tool_definitions()
            if plan_version in item.versions and item.handler_name is not None}
