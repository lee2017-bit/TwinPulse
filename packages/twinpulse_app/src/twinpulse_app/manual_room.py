# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A user-dimensioned photo room, without claiming photo interpretation."""

from __future__ import annotations

import math

from twinpulse_core import SiteToolPlan
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_core.site_tools import SiteCallEvidence, validate_site_tool_plan
from twinpulse_core.furniture import FURNITURE_CATALOG_VERSION, furniture_footprint, furniture_kinds
from twinpulse_core.model_library import PARAMETRIC_FURNITURE_VERSION, validate_furniture_parameters


def _furniture_calls(items: object, width: float, length: float) -> tuple[SceneToolCall, ...]:
    if not isinstance(items, (list, tuple)) or len(items) > 12:
        raise ValueError("room furniture must be a list of at most twelve selections")
    calls: list[SceneToolCall] = []
    footprints: list[tuple[float, float, float, float]] = []
    for index, item in enumerate(items, start=1):
        basic={'kind','center_m','yaw_deg'}
        if not isinstance(item, dict) or set(item) not in (basic,basic|{'dimensions_m','variant','finish'}):
            raise ValueError("room furniture selection shape is invalid")
        parametric='dimensions_m' in item
        kind = item["kind"]
        center = item["center_m"]
        yaw = item["yaw_deg"]
        if (not isinstance(kind, str) or kind not in furniture_kinds()
                or not isinstance(center, (list, tuple)) or len(center) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in center)
                or type(yaw) not in (int, float) or not math.isfinite(yaw) or not -180 <= yaw <= 180):
            raise ValueError("room furniture position or type is invalid")
        sx, sy = validate_furniture_parameters(item)[:2] if parametric else furniture_footprint(kind)
        angle = math.radians(yaw)
        half_x = (abs(math.cos(angle)) * sx + abs(math.sin(angle)) * sy) / 2
        half_y = (abs(math.sin(angle)) * sx + abs(math.cos(angle)) * sy) / 2
        x, y = (float(value) for value in center)
        if abs(x) + half_x > width / 2 - 0.1 or abs(y) + half_y > length / 2 - 0.1:
            raise ValueError("room furniture extends outside the user-entered floor")
        if any(abs(x - px) < half_x + phx and abs(y - py) < half_y + phy
               for px, py, phx, phy in footprints):
            raise ValueError("room furniture footprints overlap")
        footprints.append((x, y, half_x, half_y))
        calls.append(SceneToolCall(f"furniture_{index}", "place_furniture", {
            "id": f"furn_{index}_{kind}", "kind": kind,
            "catalog_version": PARAMETRIC_FURNITURE_VERSION if parametric else FURNITURE_CATALOG_VERSION,
            "center_m": [x, y], "yaw_deg": float(yaw),
            **({key:item[key] for key in ('dimensions_m','variant','finish')} if parametric else {}),
        }))
    return tuple(calls)


def manual_room_plan(project_id: str, width_m: object, length_m: object,
                     wall_height_m: object, furniture: object = (), room_items: object = ()) -> SiteToolPlan:
    values = (width_m, length_m, wall_height_m)
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
            or not 1.0 <= width_m <= 12.0 or not 1.0 <= length_m <= 12.0
            or not 1.8 <= wall_height_m <= 4.0):
        raise ValueError("room dimensions must be finite user-entered metres")
    width, length, height = (float(value) for value in values)
    thickness = 0.08
    shell_calls = (
        SceneToolCall("floor", "create_floor", {
            "id": "floor", "center_m": [0.0, 0.0], "size_m": [width, length],
        }),
        SceneToolCall("left_wall", "create_wall", {
            "id": "left_wall", "position_m": [-width / 2, 0.0, height / 2],
            "dimensions_m": [thickness, length, height], "yaw_deg": 0.0,
        }),
        SceneToolCall("right_wall", "create_wall", {
            "id": "right_wall", "position_m": [width / 2, 0.0, height / 2],
            "dimensions_m": [thickness, length, height], "yaw_deg": 0.0,
        }),
        SceneToolCall("back_wall", "create_wall", {
            "id": "back_wall", "position_m": [0.0, length / 2, height / 2],
            "dimensions_m": [width, thickness, height], "yaw_deg": 0.0,
        }),
    )
    furniture_calls = _furniture_calls(furniture, width, length)
    if not isinstance(room_items, (list, tuple)) or len(room_items) > 24:
        raise ValueError('room items must contain at most 24 typed selections')
    from twinpulse_core.room_items import checked_room_item
    item_calls = tuple(SceneToolCall(f'room_item_{i}', 'place_room_item', checked_room_item(dict(item)))
                       for i, item in enumerate(room_items, start=1))
    calls = shell_calls + furniture_calls + item_calls
    evidence = tuple(SiteCallEvidence(call.call_id, (), "user",
                                      "User-entered approximate room item and synthetic risk envelope; not measured"
                                      if call.tool == "place_room_item" else
                                      "User-selected local furniture preset; photo not interpreted"
                                      if call.tool == "place_furniture" else
                                      "User-entered room dimensions; photo not measured or interpreted")
                     for call in calls)
    return validate_site_tool_plan(SiteToolPlan(
        scene_id=f"room_{project_id}"[:64],
        summary="User-dimensioned rectangular room; photo retained, not interpreted",
        image_observations="No visual inference was performed. Front wall is open for viewing.",
        calls=calls, call_evidence=evidence,
        plan_version="2.2" if item_calls or any(call.arguments.get('catalog_version')==PARAMETRIC_FURNITURE_VERSION
                                               for call in furniture_calls) else "2.1" if furniture_calls else "2.0",
    ))
