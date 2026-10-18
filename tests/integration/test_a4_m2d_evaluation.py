# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A4 must preserve M2-D drawing failures without a model or Isaac call."""

import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "twinpulse_core" / "src"))
from twinpulse_core import evaluate_m2d_score  # noqa: E402


class A4M2dEvaluationTests(unittest.TestCase):
    def test_reference_and_two_wrong_rack_heights_keep_separate_axes(self):
        manifest_path = ROOT / "fixtures" / "m2d" / "dimensioned_floorplan.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with TemporaryDirectory() as folder:
            root = Path(folder)
            reference_path = root / "reference.json"
            subprocess.run([sys.executable, str(ROOT / "scripts" / "create_m2d_reference_report.py"),
                            "--manifest", str(manifest_path), "--output", str(reference_path)],
                           check=True, capture_output=True, text=True)
            good_score = root / "good-score.json"
            good_a4 = root / "good-a4.json"
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_m2d_floorplan_result.py"),
                                     "--manifest", str(manifest_path), "--provider-report", str(reference_path),
                                     "--output", str(good_score), "--a4-output", str(good_a4)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads(good_score.read_text(encoding="utf-8"))
            report = json.loads(good_a4.read_text(encoding="utf-8"))
            self.assertEqual((score["passed_checks"], score["total_checks"]), (29, 29))
            self.assertEqual(report["axes"]["scene_fidelity"]["status"], "PASS")
            self.assertIsNone(report["axes"]["collision"]["count"])
            self.assertIsNone(report["overall_score"])

            bad_provider = copy.deepcopy(json.loads(reference_path.read_text(encoding="utf-8")))
            for call in bad_provider["fixtures"][0]["plan"]["calls"]:
                if call["tool"] == "create_rack_row":
                    call["arguments"]["height_m"] = 2.0
            bad_provider_path = root / "bad-provider.json"
            bad_provider_path.write_text(json.dumps(bad_provider), encoding="utf-8")
            bad_score = root / "bad-score.json"
            bad_a4 = root / "bad-a4.json"
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_m2d_floorplan_result.py"),
                                     "--manifest", str(manifest_path), "--provider-report", str(bad_provider_path),
                                     "--output", str(bad_score), "--a4-output", str(bad_a4)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            failed = json.loads(bad_score.read_text(encoding="utf-8"))
            separated = json.loads(bad_a4.read_text(encoding="utf-8"))
            self.assertEqual((failed["passed_checks"], failed["total_checks"]), (27, 29))
            self.assertEqual(separated["axes"]["scene_fidelity"]["status"], "FAIL")
            self.assertEqual(separated["axes"]["scene_fidelity"]["failed_check_names"],
                             ["rack_1_height_m", "rack_2_height_m"])
            self.assertEqual(separated["axes"]["simulation_quality"]["status"], "NOT_RUN")
            self.assertEqual(separated["axes"]["task_success"]["status"], "NOT_RUN")
            self.assertFalse(separated["motion_authorized"])

            forged = copy.deepcopy(failed)
            forged["status"] = "PASS"
            with self.assertRaises(ValueError):
                evaluate_m2d_score(forged, manifest)
            forged = copy.deepcopy(failed)
            forged["image_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                evaluate_m2d_score(forged, manifest)
            forged = copy.deepcopy(score)
            forged["checks"][0]["name"] = "invented_check"
            with self.assertRaises(ValueError):
                evaluate_m2d_score(forged, manifest)


if __name__ == "__main__":
    unittest.main()
