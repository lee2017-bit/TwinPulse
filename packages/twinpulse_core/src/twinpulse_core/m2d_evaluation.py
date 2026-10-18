# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only A4 projection of the fixed M2-D 29-check scorer result.

This does not re-score a tool plan or authenticate an imported report. The
existing scorer remains the source of each individual drawing check.
"""

from collections.abc import Mapping

from .revisions import canonical_sha256

_FIXED_CHECK_NAMES = frozenset({
    "one_floor", "floor_center_m", "floor_size_m", "two_rack_rows",
    *(f"rack_{index}_{name}" for index in (1, 2)
      for name in ("center_m", "length_m", "depth_m", "height_m", "bay_count")),
    "four_perimeter_walls", "perimeter_wall_height_m",
    *(f"wall_{side}_{name}" for side in ("north", "south", "east", "west")
      for name in ("position_m", "span_m")),
    "one_driven_agv", "agv_start_position_m", "one_navigation_task",
    "goal_position_m", "route_length_m",
})


def evaluate_m2d_score(score: Mapping[str, object], manifest: Mapping[str, object]) -> dict:
    if not isinstance(score, Mapping) or not isinstance(manifest, Mapping):
        raise ValueError("M2-D score and fixed manifest are required")
    fixtures = manifest.get("fixtures")
    if (manifest.get("schema_version") != "1.0" or type(fixtures) is not list
            or len(fixtures) != 1 or type(fixtures[0]) is not dict):
        raise ValueError("fixed M2-D fixture manifest required")
    fixture = fixtures[0]
    if (score.get("schema_version") != "1.0" or score.get("evaluation_id") != manifest.get("evaluation_id")
            or score.get("fixture_id") != fixture.get("id")
            or score.get("image_sha256") != fixture.get("sha256")):
        raise ValueError("M2-D score does not bind to the fixed image and evaluation")
    checks = score.get("checks")
    if (type(checks) is not list or len(checks) != 29
            or any(type(item) is not dict or type(item.get("name")) is not str
                   or type(item.get("passed")) is not bool for item in checks)
            or {item["name"] for item in checks} != _FIXED_CHECK_NAMES):
        raise ValueError("M2-D 29-check result is malformed")
    measurement = score.get("measurement_validation")
    if (type(measurement) is not dict or measurement.get("status") not in ("PASS", "FAIL")
            or type(measurement.get("constraint_count")) is not int
            or measurement["constraint_count"] != 8):
        raise ValueError("M2-D independent measurement result is malformed")
    passed = sum(item["passed"] for item in checks)
    expected_pass = passed == 29 and measurement["status"] == "PASS"
    if (type(score.get("passed_checks")) is not int or score["passed_checks"] != passed
            or type(score.get("total_checks")) is not int or score["total_checks"] != 29
            or score.get("build_allowed") is not expected_pass
            or score.get("status") != ("PASS" if expected_pass else "FAIL")):
        raise ValueError("M2-D score summary contradicts its checks")
    body = {
        "schema_version": "adaptive-evaluation-1.0", "mode": "fixed_m2d_drawing_offline",
        "evaluation_id": score["evaluation_id"], "fixture_id": score["fixture_id"],
        "input_image_sha256": score["image_sha256"],
        "manifest_digest": canonical_sha256(manifest), "source_score_digest": canonical_sha256(score),
        "axes": {
            "scene_fidelity": {"status": "PASS" if expected_pass else "FAIL",
                               "basis": "fixed_dimensioned_drawing_29_checks_and_independent_measurements",
                               "passed_checks": passed, "total_checks": 29,
                               "measurement_status": measurement["status"],
                               "failed_check_names": [item["name"] for item in checks if not item["passed"]]},
            "simulation_quality": {"status": "NOT_RUN", "basis": "score_contains_no_isaac_episode"},
            "task_success": {"status": "NOT_RUN", "basis": "score_contains_no_rollout"},
            "latency": {"status": "NOT_MEASURED", "basis": "no_wall_clock_receipt"},
            "cost": {"status": "UNKNOWN", "basis": "no_pricing_or_usage_receipt"},
            "tool_validity": {"status": "NOT_EVALUATED", "basis": "drawing_score_is_not_tool_schema_audit"},
            "collision": {"status": "NOT_MEASURED", "source": "none", "count": None},
        },
        "overall_score": None, "source_verified": False, "physical_validation": "NOT_RUN",
        "motion_authorized": False,
    }
    return {**body, "revision": canonical_sha256(body)}
