"""Compare a generated scene-tool plan with the M2-D floor-plan ground truth."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = REPO_ROOT / "packages" / "twinpulse_core" / "src"
PROVIDER_SRC = REPO_ROOT / "packages" / "twinpulse_provider" / "src"
for source in (CORE_SRC, PROVIDER_SRC):
    sys.path.insert(0, str(source))

from twinpulse_core import SceneToolPlan  # noqa: E402
from twinpulse_provider import (  # noqa: E402
    MeasurementConstraint,
    MeasurementConstraintError,
    validate_measurement_constraints,
)
from m2d_measurements import constraints_from_ground_truth


def _near(actual: float, expected: float, tolerance: float) -> bool:
    return math.isclose(float(actual), float(expected), abs_tol=tolerance)


def _vector_near(actual: list[float], expected: list[float], tolerance: float) -> bool:
    return len(actual) == len(expected) and all(_near(a, e, tolerance) for a, e in zip(actual, expected, strict=True))


def _call_args(calls: list[dict[str, Any]], tool: str) -> list[dict[str, Any]]:
    return [dict(call["arguments"]) for call in calls if call.get("tool") == tool]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--provider-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = json.loads(args.provider_report.read_text(encoding="utf-8"))
    truth = manifest["ground_truth"]
    fixtures = report.get("fixtures", [])
    if len(fixtures) != 1 or fixtures[0].get("status") != "PASS":
        raise RuntimeError("provider report must contain one successful M2-D fixture")
    fixture = fixtures[0]
    calls = fixture["plan"]["calls"]
    declared_constraints = tuple(
        MeasurementConstraint.from_dict(value)
        for value in constraints_from_ground_truth(truth)
    )
    measurement_validation: dict[str, Any]
    try:
        measurement_receipt = validate_measurement_constraints(
            SceneToolPlan.from_dict(fixture["plan"]),
            declared_constraints,
        )
        measurement_validation = {
            "status": "PASS",
            "constraint_count": measurement_receipt.constraint_count,
            "checked_value_count": measurement_receipt.checked_value_count,
        }
    except MeasurementConstraintError as error:
        measurement_validation = {
            "status": "FAIL",
            "constraint_count": len(declared_constraints),
            "error": str(error),
        }

    floors = _call_args(calls, "create_floor")
    racks = sorted(_call_args(calls, "create_rack_row"), key=lambda item: float(item["center_m"][1]))
    walls = _call_args(calls, "create_wall")
    robots = _call_args(calls, "place_predefined_agv")
    tasks = _call_args(calls, "create_navigation_task")

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, actual: Any, expected: Any, tolerance: Any = None) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "actual": actual,
                "expected": expected,
                "tolerance": tolerance,
            }
        )

    check("one_floor", len(floors) == 1, len(floors), 1)
    floor = floors[0] if floors else {}
    floor_center = floor.get("center_m", [])
    floor_size = floor.get("size_m", [])
    check("floor_center_m", _vector_near(floor_center, truth["floor_center_m"], 0.5), floor_center, truth["floor_center_m"], 0.5)
    check("floor_size_m", _vector_near(floor_size, truth["floor_size_m"], 0.5), floor_size, truth["floor_size_m"], 0.5)
    check("two_rack_rows", len(racks) == 2, len(racks), 2)
    expected_centers = sorted(truth["rack_centers_m"], key=lambda item: float(item[1]))
    for index, expected_center in enumerate(expected_centers, start=1):
        rack = racks[index - 1] if index <= len(racks) else {}
        prefix = f"rack_{index}"
        center = rack.get("center_m", [])
        check(f"{prefix}_center_m", _vector_near(center, expected_center, 0.5), center, expected_center, 0.5)
        for field, tolerance in (("length_m", 0.5), ("depth_m", 0.25), ("height_m", 0.25)):
            expected = truth[f"rack_{field}"]
            actual = rack.get(field)
            check(f"{prefix}_{field}", actual is not None and _near(actual, expected, tolerance), actual, expected, tolerance)
        bay_count = rack.get("bay_count")
        check(f"{prefix}_bay_count", bay_count is not None and int(bay_count) == int(truth["rack_bay_count"]), bay_count, truth["rack_bay_count"])

    check("four_perimeter_walls", len(walls) == 4, len(walls), 4)
    heights = [float(wall["dimensions_m"][2]) for wall in walls]
    check(
        "perimeter_wall_height_m",
        len(walls) == 4 and all(_near(height, truth["perimeter_wall_height_m"], 0.25) for height in heights),
        heights,
        truth["perimeter_wall_height_m"],
        0.25,
    )
    floor_x, floor_y = (float(value) for value in truth["floor_size_m"])
    wall_z = float(truth["perimeter_wall_height_m"]) / 2.0
    expected_walls = (
        ("north", [0.0, floor_y / 2.0, wall_z], floor_x),
        ("south", [0.0, -floor_y / 2.0, wall_z], floor_x),
        ("east", [floor_x / 2.0, 0.0, wall_z], floor_y),
        ("west", [-floor_x / 2.0, 0.0, wall_z], floor_y),
    )
    unmatched_walls = list(walls)
    for name, expected_position, expected_span in expected_walls:
        wall = min(
            unmatched_walls,
            key=lambda item: math.hypot(float(item["position_m"][0]) - expected_position[0], float(item["position_m"][1]) - expected_position[1]),
            default={},
        )
        if wall:
            unmatched_walls.remove(wall)
        position = wall.get("position_m", [])
        dimensions = wall.get("dimensions_m", [])
        horizontal_span = max((float(value) for value in dimensions[:2]), default=None)
        check(f"wall_{name}_position_m", _vector_near(position, expected_position, 0.5), position, expected_position, 0.5)
        check(
            f"wall_{name}_span_m",
            horizontal_span is not None and _near(horizontal_span, expected_span, 0.5),
            horizontal_span,
            expected_span,
            0.5,
        )

    check("one_driven_agv", len(robots) == 1, len(robots), 1)
    start = robots[0]["start_position_m"] if robots else []
    check("agv_start_position_m", _vector_near(start, truth["agv_start_position_m"], 0.25), start, truth["agv_start_position_m"], 0.25)
    check("one_navigation_task", len(tasks) == 1, len(tasks), 1)
    goal = tasks[0]["goal_position_m"] if tasks else []
    check("goal_position_m", _vector_near(goal, truth["goal_position_m"], 0.25), goal, truth["goal_position_m"], 0.25)
    if start and goal:
        route_length = math.hypot(float(goal[0]) - float(start[0]), float(goal[1]) - float(start[1]))
        check("route_length_m", _near(route_length, truth["route_length_m"], 0.25), route_length, truth["route_length_m"], 0.25)
    else:
        check("route_length_m", False, None, truth["route_length_m"], 0.25)

    passed_count = sum(item["passed"] for item in checks)
    result = {
        "schema_version": "1.0",
        "evaluation_id": manifest["evaluation_id"],
        "fixture_id": fixture["fixture_id"],
        "image_sha256": fixture["image_sha256"],
        "image_observations": fixture.get("image_observations", ""),
        "checks": checks,
        "passed_checks": passed_count,
        "total_checks": len(checks),
        "measurement_validation": measurement_validation,
        "build_allowed": passed_count == len(checks) and measurement_validation["status"] == "PASS",
        "status": (
            "PASS"
            if passed_count == len(checks) and measurement_validation["status"] == "PASS"
            else "FAIL"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={args.output}")
    print(f"status={result['status']} checks={passed_count}/{len(checks)}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
