# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Run an explicit no-device fixture subset of the DP0 demo operation inventory.

This does not execute the robot, discover tests dynamically, or grant demo readiness.
An operation with a passing fixture can still have product, integration and physical gaps.
"""

import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages/twinpulse_core/src"))
from twinpulse_core.demo_contract import OPERATIONS, audit  # noqa: E402


# Reviewed fixed local fixtures only. Do not turn manifest test IDs into executable
# input: some are physical tests, and future test modules may have side effects.
SAFE_CASES = {
    "project_scene_open": "tests.integration.test_a2_project_catalog.ProjectCatalogTests.test_explicit_saved_bedroom_project_is_reviewable_and_does_not_switch",
    "room_goal_preview": "packages.twinpulse_core.tests.test_room_goal.RoomGoalTests.test_rigid_direction_correct_and_no_authority",
    "source_prepare": "tests.integration.test_robot_preparation.PreparationTests.test_archive_reproducible_and_contains_sources_not_keys",
    "stationary_raw_odom_scan_tf": "packages.twinpulse_robot_safety.tests.stationary_test.StationaryTests.test_passive_capture_keeps_bounded_invalid_odom_and_no_motion_authority",
    "ros_lidar_start_scan_stop": "packages.twinpulse_robot_safety.tests.test_lidar_capture.CaptureTest.test_normal",
    "forward_motion": "tests.integration.test_physical_controller.PhysicalHttpTests.test_http_forward_input_reaches_fake_owned_pipe",
    "reverse_motion": "tests.integration.test_physical_controller.PhysicalHttpTests.test_http_reverse_input_reaches_fake_owned_pipe",
    "left_turn": "tests.integration.test_physical_controller.PhysicalHttpTests.test_http_left_input_reaches_fake_owned_pipe",
    "right_turn": "tests.integration.test_physical_controller.PhysicalHttpTests.test_http_right_input_reaches_fake_owned_pipe",
    "graceful_stop": "tests.integration.test_physical_controller.PhysicalHttpTests.test_http_graceful_stop_reaches_fake_owned_pipe",
    "force_stop": "tests.integration.test_physical_controller.PhysicalHttpTests.test_http_force_stop_reaches_fake_owned_pipe",
    "calibrated_goal": "packages.twinpulse_core.tests.test_room_goal.RoomGoalTests.test_no_reference_never_invents_coordinates",
    "autonomous_mission": "packages.twinpulse_robot_safety.tests.mission_test.MissionTests.test_local_mission_arrives_without_remote_directions_or_repeat_approval",
    "obstacle_replan": "tests.integration.test_bedroom_rehearsal.BedroomRehearsalTests.test_synthetic_obstacle_stop_replan_and_arrival_are_one_record",
    "twin_observation_replay": "tests.integration.test_bedroom_rehearsal.BedroomRehearsalTests.test_same_conditions_comparison_and_unknown_collision",
    "same_condition_comparison": "packages.twinpulse_core.tests.test_route_comparison.RouteComparisonTests.test_changed_conditions_cannot_be_compared",
    "safe_cleanup_and_export": "tests.integration.test_robot_preparation.PreparationTests.test_stationary_transfer_resumes_only_missing_files_without_rerun",
    "saved_evidence_resume": "tests.integration.test_robot_evidence_recovery.RecoveryTests.test_saved_report_retry_is_transfer_only_and_idempotent",
}

BOUNDARY_NOTES = {
    "project_scene_open": "SAVED_PROJECT_FIXTURE_NOT_USER_SESSION",
    "room_goal_preview": "SYNTHETIC_COORDINATE_PREVIEW_NO_AUTHORITY",
    "source_prepare": "LOCAL_SOURCE_BUNDLE_ONLY",
    "stationary_raw_odom_scan_tf": "FAKE_ROS_MESSAGES_NOT_RAW_CAPTURE",
    "ros_lidar_start_scan_stop": "FAKE_PORT_NO_PHYSICAL_ROTOR_CONFIRMATION",
    "forward_motion": "APP_HTTP_TO_FAKE_OWNED_PIPE_NOT_WHEELS",
    "reverse_motion": "APP_HTTP_TO_FAKE_OWNED_PIPE_NOT_WHEELS",
    "left_turn": "APP_HTTP_TO_FAKE_OWNED_PIPE_NOT_WHEELS",
    "right_turn": "APP_HTTP_TO_FAKE_OWNED_PIPE_NOT_WHEELS",
    "graceful_stop": "APP_HTTP_TO_FAKE_PIPE_NO_PHYSICAL_STOP",
    "force_stop": "APP_HTTP_TO_FAKE_PIPE_NO_PHYSICAL_STOP",
    "calibrated_goal": "NEGATIVE_NO_REFERENCE_GUARD_ONLY",
    "autonomous_mission": "ARTIFICIAL_POSE_SCAN_NO_ROBOT_MOTION",
    "obstacle_replan": "SYNTHETIC_BEDROOM_ONLY",
    "twin_observation_replay": "SYNTHETIC_BEDROOM_REPLAY_ONLY",
    "same_condition_comparison": "NEGATIVE_CHANGED_CONDITIONS_GUARD_ONLY",
    "safe_cleanup_and_export": "FAKE_TRANSFER_RESUME_NOT_ROBOT_CLEANUP",
    "saved_evidence_resume": "FAKE_TRANSFER_RESUME_ONLY",
}


def _execute_case(test_id):
    suite = unittest.defaultTestLoader.loadTestsFromName(test_id)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    counts = {
        "run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "unexpected_successes": len(result.unexpectedSuccesses),
    }
    passed = result.testsRun == 1 and result.wasSuccessful() and not result.skipped
    return "FIXTURE_PASS" if passed else "FIXTURE_FAIL", counts


def verify(root=ROOT, execute_case=_execute_case):
    declared = {operation[0] for operation in OPERATIONS}
    if not SAFE_CASES or set(SAFE_CASES) != declared or set(BOUNDARY_NOTES) != declared:
        raise ValueError("SAFE_CASE_OPERATION_MATRIX_MISMATCH")
    audit_report = audit(root)
    audited = {row["operation_id"]: row for row in audit_report["operations"]}
    rows = []
    for operation in OPERATIONS:
        operation_id = operation[0]
        test_id = SAFE_CASES.get(operation_id)
        status, counts = execute_case(test_id) if test_id else ("NOT_SELECTED", None)
        rows.append({
            "operation_id": operation_id,
            "fixture_test_id": test_id,
            "fixture_boundary": BOUNDARY_NOTES.get(operation_id),
            "fixture_status": status,
            "fixture_counts": counts,
            "operation_audit_status": audited[operation_id]["status"],
            "contract_reasons": audited[operation_id]["contract_reasons"],
        })
    fake_http_operations = {"forward_motion", "reverse_motion", "left_turn", "right_turn",
                            "graceful_stop", "force_stop"}
    fake_http_passed = all(row["fixture_status"] == "FIXTURE_PASS" for row in rows
                           if row["operation_id"] in fake_http_operations)
    return {
        "schema_version": "demo-offline-operation-fixtures-1",
        "offline_fixture_suite_status": "PASS" if all(
            row["fixture_status"] != "FIXTURE_FAIL" for row in rows
        ) else "FAIL",
        "fixture_scope": "FIXED_NO_DEVICE_TESTS_ONLY",
        "physical_validation": "NOT_RUN",
        "product_integration_validation": ("PARTIAL_FAKE_HTTP_ONLY" if fake_http_passed
                                           else "NOT_ESTABLISHED_BY_THIS_RUN"),
        "pc_demo_ready": False,
        "manifest_mapped": audit_report["manifest_mapped"],
        "fixture_selected_count": sum(row["fixture_test_id"] is not None for row in rows),
        "fixture_pass_count": sum(row["fixture_status"] == "FIXTURE_PASS" for row in rows),
        "operations": rows,
    }


def main():
    try:
        report = verify()
    except Exception as exc:
        print(json.dumps({
            "schema_version": "demo-offline-operation-fixtures-1",
            "offline_fixture_suite_status": "ERROR",
            "error_type": type(exc).__name__,
            "physical_validation": "NOT_RUN",
            "pc_demo_ready": False,
        }, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["offline_fixture_suite_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
