# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The DP0 fixture runner must never convert fixture success into robot readiness."""

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_demo_offline_operations as runner  # noqa: E402


class OfflineOperationRunnerTests(unittest.TestCase):
    def test_explicit_allowlist_cannot_include_unknown_operation(self):
        original = dict(runner.SAFE_CASES)
        try:
            runner.SAFE_CASES["not_a_demo_operation"] = "fake"
            with self.assertRaisesRegex(ValueError, "SAFE_CASE_OPERATION_MATRIX_MISMATCH"):
                runner.verify(ROOT, execute_case=lambda _id: self.fail("test executed"))
        finally:
            runner.SAFE_CASES.clear()
            runner.SAFE_CASES.update(original)

    def test_new_operation_cannot_silently_skip_fixture_review(self):
        original = dict(runner.SAFE_CASES)
        try:
            runner.SAFE_CASES.pop("autonomous_mission")
            with self.assertRaisesRegex(ValueError, "SAFE_CASE_OPERATION_MATRIX_MISMATCH"):
                runner.verify(ROOT, execute_case=lambda _id: self.fail("test executed"))
        finally:
            runner.SAFE_CASES.clear()
            runner.SAFE_CASES.update(original)

    def test_fixture_pass_keeps_integration_and_physical_gates_closed(self):
        report = runner.verify(ROOT, execute_case=lambda _id: ("FIXTURE_PASS", {
            "run": 1, "failures": 0, "errors": 0, "skipped": 0,
            "unexpected_successes": 0,
        }))
        self.assertEqual(report["offline_fixture_suite_status"], "PASS")
        self.assertFalse(report["pc_demo_ready"])
        self.assertEqual(report["physical_validation"], "NOT_RUN")
        self.assertEqual(report["product_integration_validation"], "PARTIAL_FAKE_HTTP_ONLY")
        row = next(row for row in report["operations"] if row["operation_id"] == "forward_motion")
        self.assertEqual(row["fixture_status"], "FIXTURE_PASS")
        self.assertEqual(row["operation_audit_status"], "GAP")
        mission = next(row for row in report["operations"] if row["operation_id"] == "autonomous_mission")
        self.assertEqual(mission["fixture_boundary"], "ARTIFICIAL_POSE_SCAN_NO_ROBOT_MOTION")
        self.assertEqual(report["fixture_selected_count"], len(runner.OPERATIONS))

    def test_fixture_failure_is_visible_without_claiming_readiness(self):
        report = runner.verify(ROOT, execute_case=lambda _id: ("FIXTURE_FAIL", {
            "run": 1, "failures": 1, "errors": 0, "skipped": 0,
            "unexpected_successes": 0,
        }))
        self.assertEqual(report["offline_fixture_suite_status"], "FAIL")
        self.assertFalse(report["pc_demo_ready"])


if __name__ == "__main__":
    unittest.main()
