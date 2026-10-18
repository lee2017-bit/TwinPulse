# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Derive independent M2-D measurement expectations from one ground-truth object."""

from __future__ import annotations

from typing import Any, Mapping


def constraints_from_ground_truth(truth: Mapping[str, Any], *, source: str = "dimensioned_drawing_sidecar") -> list[dict[str, Any]]:
    def item(constraint_id: str, tool: str, path: str, expected: Any,
             tolerance: float, occurrence: int | None = None) -> dict[str, Any]:
        return {"constraint_id": constraint_id, "tool": tool, "argument_path": path,
                "expected": expected, "tolerance": tolerance, "occurrence": occurrence, "source": source}

    return [
        item("floor_size", "create_floor", "size_m", truth["floor_size_m"], 0.1, 0),
        item("rack_length", "create_rack_row", "length_m", truth["rack_length_m"], 0.1),
        item("rack_depth", "create_rack_row", "depth_m", truth["rack_depth_m"], 0.1),
        item("rack_height", "create_rack_row", "height_m", truth["rack_height_m"], 0.25),
        item("rack_bays", "create_rack_row", "bay_count", truth["rack_bay_count"], 0),
        item("wall_height", "create_wall", "dimensions_m.2", truth["perimeter_wall_height_m"], 0.1),
        item("agv_start", "place_predefined_agv", "start_position_m", truth["agv_start_position_m"], 0.1, 0),
        item("navigation_goal", "create_navigation_task", "goal_position_m", truth["goal_position_m"], 0.1, 0),
    ]
