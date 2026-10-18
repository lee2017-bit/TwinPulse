# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Compile the M2-D ground truth into an explicitly non-provider reference report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "twinpulse_core" / "src"))

from twinpulse_core import SceneToolCall, SceneToolPlan, SceneToolRegistry, bundle_to_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    fixture = manifest["fixtures"][0]
    truth = manifest["ground_truth"]
    floor_x, floor_y = truth["floor_size_m"]
    wall_height = truth["perimeter_wall_height_m"]
    wall_z = wall_height / 2.0
    rack_calls = tuple(
        SceneToolCall(
            f"rack_{index}",
            "create_rack_row",
            {
                "id": f"rack_{index}",
                "center_m": center,
                "length_m": truth["rack_length_m"],
                "depth_m": truth["rack_depth_m"],
                "height_m": truth["rack_height_m"],
                "bay_count": truth["rack_bay_count"],
                "level_count": 3,
            },
        )
        for index, center in enumerate(truth["rack_centers_m"], start=1)
    )
    plan = SceneToolPlan(
        scene_id="dimensioned_floorplan_reference_v1",
        summary="Deterministic reference extrusion of the M2-D dimensioned floor plan.",
        image_observations="Reference coordinates copied from the fixture ground truth; no provider call.",
        calls=(
            SceneToolCall(
                "floor",
                "create_floor",
                {"id": "floor", "center_m": truth["floor_center_m"], "size_m": truth["floor_size_m"]},
            ),
            SceneToolCall(
                "wall_north",
                "create_wall",
                {"id": "wall_north", "position_m": [0.0, floor_y / 2.0, wall_z], "dimensions_m": [floor_x, 0.1, wall_height], "yaw_deg": 0.0},
            ),
            SceneToolCall(
                "wall_south",
                "create_wall",
                {"id": "wall_south", "position_m": [0.0, -floor_y / 2.0, wall_z], "dimensions_m": [floor_x, 0.1, wall_height], "yaw_deg": 0.0},
            ),
            SceneToolCall(
                "wall_east",
                "create_wall",
                {"id": "wall_east", "position_m": [floor_x / 2.0, 0.0, wall_z], "dimensions_m": [floor_y, 0.1, wall_height], "yaw_deg": 90.0},
            ),
            SceneToolCall(
                "wall_west",
                "create_wall",
                {"id": "wall_west", "position_m": [-floor_x / 2.0, 0.0, wall_z], "dimensions_m": [floor_y, 0.1, wall_height], "yaw_deg": 90.0},
            ),
            *rack_calls,
            SceneToolCall(
                "driven_agv",
                "place_predefined_agv",
                {"profile_id": "agv_compact_2wd_caster_v2", "start_position_m": truth["agv_start_position_m"]},
            ),
            SceneToolCall(
                "route",
                "create_navigation_task",
                {"id": "floorplan_route", "goal_position_m": truth["goal_position_m"], "position_tolerance_m": 0.10},
            ),
        ),
    )
    bundle = SceneToolRegistry().execute(plan)
    report = {
        "schema_version": "1.0",
        "evaluation_id": "m2d_reference_compiler_3d",
        "status": "PASS",
        "provenance": "deterministic_reference_not_provider",
        "fixtures": [
            {
                "fixture_id": fixture["id"],
                "status": "PASS",
                "request_id": "m2d-reference-no-provider-call",
                "scene_id": plan.scene_id,
                "image_filename": fixture["local_filename"],
                "image_sha256": fixture["sha256"],
                "image_observations": plan.image_observations,
                "tool_call_count": len(plan.calls),
                "expanded_object_count": len(bundle.scene.objects),
                "tool_names": [call.tool for call in plan.calls],
                "plan": plan.to_dict(),
                "bundle": json.loads(bundle_to_json(bundle)),
            }
        ],
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report["report_sha256_before_self_hash"] = hashlib.sha256(canonical).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={args.output}")
    print(f"status=PASS tools={len(plan.calls)} objects={len(bundle.scene.objects)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
