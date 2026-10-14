# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pinned parametric furniture for local room authoring, not photo recognition."""

from __future__ import annotations

from math import cos, radians, sin
from typing import Any, Mapping

from .models import SceneObject, ShapeSpec, Transform
from .scene_tools import SceneToolPlanError, _number, _object_id, _vector


FURNITURE_CATALOG_VERSION = "furniture-blocks-1.0"
# (part, local x/y, bottom, width/depth/height), metres. Origin is footprint centre.
_PRESETS: dict[str, tuple[tuple[str, float, float, float, float, float, float], ...]] = {
    "bed": (("base", 0, 0, 0, 1.4, 2.0, .28), ("mattress", 0, 0, .28, 1.36, 1.94, .18),
            ("headboard", 0, .94, 0, 1.4, .12, .9)),
    "wardrobe": (("body", 0, 0, 0, 1.2, .6, 1.9), ("door_left", -.3, -.31, .08, .58, .025, 1.72),
                 ("door_right", .3, -.31, .08, .58, .025, 1.72)),
    "desk": (("top", 0, 0, .68, 1.2, .6, .06), ("leg_fl", -.53, -.23, 0, .06, .06, .68),
             ("leg_fr", .53, -.23, 0, .06, .06, .68), ("leg_bl", -.53, .23, 0, .06, .06, .68),
             ("leg_br", .53, .23, 0, .06, .06, .68)),
    "chair": (("seat", 0, 0, .42, .46, .44, .06), ("back", 0, .19, .48, .46, .06, .45),
              ("leg_fl", -.19, -.17, 0, .05, .05, .42), ("leg_fr", .19, -.17, 0, .05, .05, .42),
              ("leg_bl", -.19, .17, 0, .05, .05, .42), ("leg_br", .19, .17, 0, .05, .05, .42)),
    "sofa": (("seat", 0, -.08, .32, 1.6, .7, .18), ("back", 0, .31, .25, 1.6, .16, .6),
             ("left_arm", -.74, -.08, .25, .12, .7, .4), ("right_arm", .74, -.08, .25, .12, .7, .4),
             ("base", 0, 0, 0, 1.6, .8, .32)),
    "dining_table": (("top", 0, 0, .71, 1.4, .8, .06),
                     ("leg_fl", -.62, -.32, 0, .07, .07, .71), ("leg_fr", .62, -.32, 0, .07, .07, .71),
                     ("leg_bl", -.62, .32, 0, .07, .07, .71), ("leg_br", .62, .32, 0, .07, .07, .71)),
    "storage": (("body", 0, 0, 0, .8, .4, .9), ("left_door", -.2, -.21, .04, .38, .025, .8),
                ("right_door", .2, -.21, .04, .38, .025, .8)),
}


def furniture_kinds() -> tuple[str, ...]:
    return tuple(_PRESETS)


def furniture_footprint(kind: str) -> tuple[float, float]:
    if kind not in _PRESETS:
        raise SceneToolPlanError("furniture kind is unsupported")
    parts = _PRESETS[kind]
    return (max(abs(dx) + sx / 2 for _, dx, _, _, sx, _, _ in parts) * 2,
            max(abs(dy) + sy / 2 for _, _, dy, _, _, sy, _ in parts) * 2)


def expand_furniture(arguments: Mapping[str, Any]) -> tuple[SceneObject, ...]:
    from .model_library import PARAMETRIC_FURNITURE_VERSION, parametric_parts
    parametric = arguments.get('catalog_version') == PARAMETRIC_FURNITURE_VERSION
    fields = {"id", "kind", "catalog_version", "center_m", "yaw_deg"}
    if parametric:
        fields |= {'dimensions_m','variant','finish'}
    if set(arguments) != fields:
        raise SceneToolPlanError("furniture arguments are invalid")
    base_id = _object_id(arguments["id"], maximum_length=48)
    kind = arguments["kind"]
    if not isinstance(kind, str) or kind not in _PRESETS:
        raise SceneToolPlanError("furniture kind is unsupported")
    if arguments["catalog_version"] != FURNITURE_CATALOG_VERSION and not parametric:
        raise SceneToolPlanError("furniture catalog version is unsupported")
    center = _vector(arguments["center_m"], 2, "center_m")
    yaw = _number(arguments["yaw_deg"], "yaw_deg", minimum=-180.0, maximum=180.0)
    c, s = cos(radians(yaw)), sin(radians(yaw))
    result = []
    parts = parametric_parts(arguments) if parametric else _PRESETS[kind]
    for part, dx, dy, bottom, sx, sy, height in parts:
        part_id = f"{base_id}_{part}"
        if len(part_id) > 64:
            raise SceneToolPlanError("furniture part id exceeds 64 characters")
        result.append(SceneObject(part_id, "equipment",
                                  Transform((center[0] + dx*c - dy*s,
                                             center[1] + dx*s + dy*c, bottom + height/2),
                                            (0.0, 0.0, yaw)),
                                  ShapeSpec("box", (sx, sy, height))))
    return tuple(result)


def validate_furniture_layout(objects: tuple[SceneObject, ...],
                              groups: tuple[tuple[str, ...], ...]) -> None:
    """Conservatively reject furniture outside the floor or across other solids."""
    if not groups:
        return
    floor = next((item for item in objects if item.kind == "floor"), None)
    if floor is None:
        raise SceneToolPlanError("furniture requires a floor")

    def bounds(item: SceneObject) -> tuple[float, float, float, float]:
        x, y, _ = item.transform.position_m
        if item.shape.type == "box":
            sx, sy = item.shape.dimensions_m[:2]
            angle = radians(item.transform.rotation_rpy_deg[2])
            hx = (abs(cos(angle)) * sx + abs(sin(angle)) * sy) / 2
            hy = (abs(sin(angle)) * sx + abs(cos(angle)) * sy) / 2
        elif item.shape.type == "cylinder":
            hx = hy = item.shape.dimensions_m[0]
        else:
            raise SceneToolPlanError("furniture clearance requires supported geometry")
        return x - hx, x + hx, y - hy, y + hy

    floor_bounds = bounds(floor)
    by_id = {item.id: item for item in objects}
    furniture_ids = {item_id for group in groups for item_id in group}
    other_solids = [item for item in objects if item.id not in furniture_ids and item.kind != "floor"
                    and item.collision]
    group_bounds: list[tuple[float, float, float, float]] = []
    for group in groups:
        parts = [bounds(by_id[item_id]) for item_id in group]
        current = (min(part[0] for part in parts), max(part[1] for part in parts),
                   min(part[2] for part in parts), max(part[3] for part in parts))
        if (current[0] < floor_bounds[0] + .1 or current[1] > floor_bounds[1] - .1
                or current[2] < floor_bounds[2] + .1 or current[3] > floor_bounds[3] - .1):
            usable = (floor_bounds[0]+.1, floor_bounds[1]-.1,
                      floor_bounds[2]+.1, floor_bounds[3]-.1)
            raise SceneToolPlanError("furniture extends outside the floor clearance: "
                f"group={group[0]}, footprint_bounds_xy="
                f"{tuple(round(v, 4) for v in current)}, usable_floor_bounds_xy="
                f"{tuple(round(v, 4) for v in usable)}; adjust this group's centre/yaw, not the requested floor size")
        group_bounds.append(current)

    def intersects(left: tuple[float, float, float, float],
                   right: tuple[float, float, float, float]) -> bool:
        return left[0] < right[1] and right[0] < left[1] and left[2] < right[3] and right[2] < left[3]

    for index, current in enumerate(group_bounds):
        for other_index in range(index+1,len(group_bounds)):
            other=group_bounds[other_index]
            if intersects(current,other):
                raise SceneToolPlanError("furniture footprints overlap: "
                    f"groups={groups[index][0]},{groups[other_index][0]}, "
                    f"bounds_xy={tuple(round(v,4) for v in current)},{tuple(round(v,4) for v in other)}; "
                    "separate their X or Y intervals; distinct objects cannot share the same centre")
        for other in other_solids:
            if intersects(current,bounds(other)):
                raise SceneToolPlanError("furniture overlaps another scene object: "
                    f"group={groups[index][0]}, other={other.id}")
