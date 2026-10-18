# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.summarize_offline_rehearsal import APP_CHECKS, IMAGES, STAGES, collect, render_html, write_summary


class OfflineSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "regression").mkdir()
        (self.root / "browser").mkdir()
        self.regression = {"status": "PASS", "app": APP_CHECKS, "isaac": "NOT_RUN",
                           "artifact_dir": str(self.root / "regression")}
        self.app = {"schema_version": "offline-app-rehearsal-1.0", "status": "PASS", "data": "synthetic",
                    "http": "actual_local_backend", "robot": "NOT_RUN", "isaac": "NOT_RUN", "provider_calls": "NOT_RUN",
                    "active_project_changed": False, "browser_stages": list(STAGES)}
        self.browser = {"status": "PASS", "data": "synthetic", "http": "actual_local_backend",
                        "physical_validation": "NOT_RUN", "external_requests": 0, "page_errors": 0,
                        "engine_commands": 0, "stages": list(STAGES)}
        for name, _label in IMAGES:
            (self.root / "browser" / name).write_bytes(b"\x89PNG\r\n\x1a\nfixture-not-renderable")
        self.put("browser/browser-export.json", {"execution_authority": False, "restore_supported": False})
        self.save()

    def put(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding="utf-8-sig")

    def save(self):
        self.put("regression/manifest.json", self.regression)
        self.put("browser/result.json", self.app)
        self.put("browser/browser-result.json", self.browser)

    def test_complete_evidence_only_passes_offline(self):
        result = collect(self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["physical_demo_ready"])
        self.assertFalse(result["motion_authorized"])
        self.assertEqual(result["current_robot_state"], "UNKNOWN")
        self.assertEqual(len(result["evidence"]), 4)
        self.assertEqual(len(result["screenshots"]), 5)

    def test_each_missing_source_or_image_is_fail(self):
        for path in ["regression/manifest.json", "browser/result.json", "browser/browser-result.json",
                     "browser/browser-export.json", "browser/map-proposal-mobile.png"]:
            with self.subTest(path=path):
                file = self.root / path
                content = file.read_bytes()
                file.unlink()
                self.assertEqual(collect(self.root)["status"], "FAIL")
                file.write_bytes(content)

    def test_each_failed_phase_is_preserved(self):
        for source in [self.regression, self.app, self.browser]:
            source["status"] = "FAIL"
            self.save()
            self.assertEqual(collect(self.root)["status"], "FAIL")
            source["status"] = "PASS"

    def test_missing_reordered_or_extra_browser_stage_fails(self):
        for stages in [list(STAGES[:-1]), list(reversed(STAGES)), list(STAGES) + ["extra"]]:
            self.browser["stages"] = stages
            self.save()
            self.assertEqual(collect(self.root)["status"], "FAIL")

    def test_no_latest_pass_or_other_manifest_directory(self):
        self.regression["artifact_dir"] = str(self.root.parent / "other-run/regression")
        self.save()
        self.assertFalse(collect(self.root)["checks"]["regression_directory_binding"])

    def test_false_counts_are_not_integer_zero(self):
        for count in [False, None, "0", 1]:
            self.browser["engine_commands"] = count
            self.save()
            self.assertEqual(collect(self.root)["status"], "FAIL")

    def test_authority_or_non_synthetic_claim_rejected(self):
        original = copy.deepcopy(self.app)
        for key, value in [("data", "physical"), ("robot", "PASS"), ("provider_calls", "PASS"),
                           ("active_project_changed", True), ("active_project_changed", 0)]:
            self.app = {**original, key: value}
            self.save()
            self.assertEqual(collect(self.root)["status"], "FAIL")

    def test_duplicate_nonfinite_and_nonobject_json_rejected(self):
        for raw in ['{"status":"FAIL","status":"PASS"}', '{"x":NaN}', '[]', '{bad']:
            (self.root / "browser/result.json").write_text(raw, encoding="utf-8")
            self.assertEqual(collect(self.root)["status"], "FAIL")

    def test_unknown_strings_not_copied_to_output(self):
        self.app["error"] = '<script>SECRET_CANARY</script>'
        self.save()
        result = collect(self.root)
        self.assertNotIn("SECRET_CANARY", json.dumps(result) + render_html(result))
        self.assertNotIn("<script", render_html(result))
        self.assertIn("SYNTHETIC INPUTS", render_html(result))

    def test_hash_changes_when_evidence_changes(self):
        before = collect(self.root)["evidence"][1]["sha256"]
        self.app["unused"] = "changed"
        self.save()
        self.assertNotEqual(before, collect(self.root)["evidence"][1]["sha256"])

    def test_summary_writes_exclusively_and_preserves_fail(self):
        self.browser["status"] = "FAIL"
        self.save()
        self.assertEqual(write_summary(self.root)["status"], "FAIL")
        original = (self.root / "summary.json").read_bytes()
        with self.assertRaises(FileExistsError):
            write_summary(self.root)
        self.assertEqual(original, (self.root / "summary.json").read_bytes())

    def test_oversized_source_and_export_authority_rejected(self):
        self.put("browser/browser-export.json", {"execution_authority": True, "restore_supported": False})
        self.assertFalse(collect(self.root)["checks"]["inspection_export"])
        (self.root / "browser/result.json").write_bytes(b" " * 2_000_001)
        self.assertIn("missing_or_invalid:browser/result.json", collect(self.root)["problems"])


if __name__ == "__main__":
    unittest.main()
