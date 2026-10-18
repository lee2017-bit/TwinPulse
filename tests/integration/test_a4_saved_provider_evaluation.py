# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Historical stored M2-C plans are not paid probes or photo ground truth."""

import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
for package in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))

from twinpulse_app.evaluation_report import evaluate_saved_provider_report  # noqa: E402
from twinpulse_core.revisions import canonical_sha256  # noqa: E402


REPORT = ROOT / "artifacts/runs/20260924-185750-s2d-replay/stored-provider-results.json"
MANIFEST = ROOT / "fixtures/m2c/warehouse_images.json"


class A4SavedProviderEvaluationTests(unittest.TestCase):
    def test_real_stored_plans_have_local_tool_validity_not_unobserved_quality(self):
        result = evaluate_saved_provider_report(REPORT, MANIFEST)
        self.assertEqual(result["revision"], canonical_sha256({k: v for k, v in result.items() if k != "revision"}))
        self.assertEqual(result["data_partition"], "historical_regression_not_held_out")
        self.assertEqual(len(result["fixtures"]), 3)
        self.assertFalse(result["source_verified"])
        self.assertFalse(result["motion_authorized"])
        self.assertIsNone(result["overall_score"])
        for item in result["fixtures"]:
            axes = item["axes"]
            self.assertEqual(axes["tool_validity"]["status"], "PASS")
            self.assertEqual(axes["scene_fidelity"]["status"], "NOT_MEASURED")
            self.assertEqual(axes["simulation_quality"]["status"], "NOT_RUN")
            self.assertEqual(axes["latency"]["status"], "NOT_MEASURED")
            self.assertEqual(axes["cost"]["status"], "UNKNOWN")
            self.assertIsNone(axes["collision"]["count"])

    def test_input_binding_and_tool_forgery_are_rejected(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for mutation in (
                lambda m, r: m["fixtures"][0].update(sha256="0" * 64),
                lambda m, r: r["fixtures"][1].update(prompt="different input"),
                lambda m, r: r["fixtures"][0]["plan"]["calls"][0].update(tool="invented_tool"),
                lambda m, r: r.update(status="FAIL"),
            ):
                changed_manifest, changed_report = copy.deepcopy(manifest), copy.deepcopy(report)
                mutation(changed_manifest, changed_report)
                manifest_path, report_path = root / "manifest.json", root / "report.json"
                manifest_path.write_text(json.dumps(changed_manifest), encoding="utf-8")
                report_path.write_text(json.dumps(changed_report), encoding="utf-8")
                with self.assertRaises(ValueError):
                    evaluate_saved_provider_report(report_path, manifest_path)

    def test_cli_writes_once_and_does_not_overwrite(self):
        with TemporaryDirectory() as folder:
            output = Path(folder) / "evaluation.json"
            command = [sys.executable, str(ROOT / "scripts/evaluate_saved_provider_report.py"),
                       "--provider-report", str(REPORT), "--manifest", str(MANIFEST),
                       "--output", str(output)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = output.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
