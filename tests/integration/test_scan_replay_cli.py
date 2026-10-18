# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("replay_saved_scan", ROOT / "scripts/replay_saved_scan.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ScanReplayCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "preview.json"
        self.args = [str(ROOT / "fixtures/scan/synthetic-stationary.json"), "--site", "test_room",
                     "--scene-revision", "a" * 64, "--profile-digest", "b" * 64,
                     "--output", str(self.output)]

    def test_fixture_replay_and_no_overwrite(self):
        self.assertEqual(MODULE.main(self.args), 0)
        before = self.output.read_bytes()
        result = json.loads(before)
        self.assertEqual(result["provenance"], "synthetic")
        self.assertEqual(result["valid_beams"], 3)
        self.assertFalse(result["demo_ready"])
        self.assertEqual(MODULE.main(self.args), 2)
        self.assertEqual(self.output.read_bytes(), before)

    def test_wrong_site_writes_nothing(self):
        self.args[2] = "other_site"
        self.assertEqual(MODULE.main(self.args), 2)
        self.assertFalse(self.output.exists())

    def test_missing_input_writes_nothing(self):
        self.args[0] = str(Path(self.temp.name) / "missing.json")
        self.assertEqual(MODULE.main(self.args), 2)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
