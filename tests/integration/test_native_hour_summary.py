# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic file fixtures for the handoff evidence verifier, not real captures."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "packages/twinpulse_core/tests"))
from test_native_scan import fixture
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_quality import analyze_native_scan
from summarize_native_scan_hour import SOURCE_FILES, STAGES, collect, read_bounded, render


class NativeHourSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.saved = self.root / "saved"; self.native = self.root / "native"; self.regression = self.root / "regression"
        for path in (self.saved, self.native, self.regression / "regression"): path.mkdir(parents=True)
        raw, nodes, photo = b"SYNTHETIC raw fixture", b"SYNTHETIC nodes fixture", b"SYNTHETIC photo fixture"
        value = fixture()
        value["source"].update(kind="saved_sensor_recording", raw_sha256=hashlib.sha256(raw).hexdigest(), nodes_sha256=hashlib.sha256(nodes).hexdigest())
        value["photos"][0]["sha256"] = hashlib.sha256(photo).hexdigest()
        value["photos"].append(dict(value["photos"][0], role="top_view"))
        self.bundle = NativeScanBundle.from_dict(value)
        for path in (self.saved / "native-scan-bundle.json", self.native / "native-scan-bundle.json", self.native / "exported-native-scan-bundle.json"):
            self.write(path, value)
        self.write(self.saved / "native-quality.json", analyze_native_scan(self.bundle))
        for name in ("room.jpg", "top-view-window-up.jpg"): (self.saved / name).write_bytes(photo)
        scan = self.root / "artifacts/lidar-capture-20260927-1214"
        capture = scan / "lidar-20260927T031354Z-323c99a6"; capture.mkdir(parents=True)
        (capture / "raw.bin").write_bytes(raw); (scan / "nodes.ndjson").write_bytes(nodes)
        self.write(self.native / "browser-result.json", {"status": "PASS", "data": "saved_sensor_recording", "http": "actual_local_backend",
            "stages": STAGES, "bundle_digest": self.bundle.digest, "physical_validation": "NOT_RUN", "external_requests": 0, "engine_commands": 0, "page_errors": 0})
        self.write(self.native / "result.json", {"status": "PASS", "data": "saved_sensor_recording", "http": "actual_local_backend",
            "browser_stages": STAGES, "active_project_changed": False, "robot": "NOT_RUN", "isaac": "NOT_RUN", "provider_calls": "NOT_RUN",
            "source_and_build_sha256": {"fixture": "current"}})
        for name in ("native-photo-review-desktop.png", "native-photo-review-mobile.png"):
            (self.native / name).write_bytes(b"\x89PNG\r\n\x1a\nSYNTHETIC")
        self.write(self.regression / "regression/manifest.json", {"fixture": True})
        (self.regression / "regression.log").write_text("Ran 1 test in 0.01s\n" * 8 + "Tests 2 passed (2)\nTWINPULSE_VERIFY_RESULT=PASS\n")
        for relative in SOURCE_FILES:
            target = self.root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_text("synthetic source")

    def tearDown(self): self.temp.cleanup()

    @staticmethod
    def write(path, value): path.write_text(json.dumps(value), encoding="utf-8")

    def collect(self):
        with patch("summarize_native_scan_hour.collect_regression", return_value={"status": "PASS"}), patch("summarize_native_scan_hour.native_source_hashes", return_value={"fixture": "current"}):
            return collect(self.root, self.saved, self.native, self.regression)

    def test_matching_records_only_offline_pass_and_static_html(self):
        result = self.collect()
        self.assertEqual(result["status"], "OFFLINE_EVIDENCE_PASS")
        self.assertEqual((result["python_tests"], result["web_tests"]), (8, 2))
        self.assertFalse(result["physical_demo_ready"])
        self.assertFalse(result["motion_authorized"])
        page = render(result)
        self.assertNotIn("<script", page)
        self.assertNotIn("https://", page)

    def test_wrong_source_build_binding_fails(self):
        path = self.native / "result.json"; value = json.loads(path.read_text()); value["source_and_build_sha256"] = {"fixture": "old"}; self.write(path, value)
        result = self.collect()
        self.assertEqual(result["status"], "EVIDENCE_CHECK_FAILED")
        self.assertFalse(result["checks"]["native_tested_source_and_build_unchanged"])

    def test_changed_photo_or_raw_fails(self):
        (self.saved / "room.jpg").write_bytes(b"other")
        raw = self.root / "artifacts/lidar-capture-20260927-1214/lidar-20260927T031354Z-323c99a6/raw.bin"
        raw.write_bytes(b"other")
        result = self.collect()
        self.assertFalse(result["checks"]["original_photo_hashes"])
        self.assertFalse(result["checks"]["original_recording_hashes"])

    def test_invented_quality_and_missing_stage_fail(self):
        path = self.saved / "native-quality.json"; value = json.loads(path.read_text()); value["clearance"] = "CLEAR"; self.write(path, value)
        path = self.native / "browser-result.json"; value = json.loads(path.read_text()); value["stages"] = STAGES[:-1]; self.write(path, value)
        result = self.collect()
        self.assertFalse(result["checks"]["quality_recomputed_exactly"])
        self.assertFalse(result["checks"]["native_browser_eight_stages"])

    def test_missing_export_not_replaced_by_another_run(self):
        (self.native / "exported-native-scan-bundle.json").unlink()
        with self.assertRaises(FileNotFoundError): self.collect()

    def test_path_escape_and_file_budget_rejected(self):
        path = self.saved / "room.jpg"
        with self.assertRaises(ValueError): read_bounded(self.native, path)
        with self.assertRaises(ValueError): read_bounded(self.root, path, 1)

    def test_windows_powershell_utf16_log_preserves_test_counts(self):
        path = self.regression / "regression.log"
        path.write_bytes(path.read_text().encode("utf-16"))
        result = self.collect()
        self.assertEqual(result["status"], "OFFLINE_EVIDENCE_PASS")
        self.assertEqual((result["python_tests"], result["web_tests"]), (8, 2))


if __name__ == "__main__": unittest.main()
