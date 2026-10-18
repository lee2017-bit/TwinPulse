# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device PC transport rejection tests; no SSH process is started."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import run_ros_scan_client as client


class ScanClientTests(unittest.TestCase):
    def test_saved_actual_scan_fixture_survives_full_fake_transport(self):
        source_dir = (client.ROOT / 'artifacts/ros-scan-20260930T143239Z-c4b681f5')
        remote_report = json.loads((source_dir / 'report.json').read_text(encoding='utf-8'))
        calls = []

        def fake(command, **_kwargs):
            calls.append(command)
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 0, b'', b'')
            if len(calls) == 2:
                return subprocess.CompletedProcess(command, 0,
                    (client._sha(client.ROOT / 'scripts/robot_ros_scan_trial.py') + '  script.py\n').encode(), b'')
            if len(calls) == 3:
                return subprocess.CompletedProcess(command, 0,
                    (json.dumps(remote_report) + '\n').encode(), b'')
            name = Path(command[-1]).name.removesuffix('.part')
            shutil.copyfile(source_dir / name, command[-1])
            return subprocess.CompletedProcess(command, 0, b'', b'')

        with tempfile.TemporaryDirectory(dir=client.ROOT / 'artifacts') as directory:
            key = Path(directory) / 'test-key'
            key.write_text('not a private key', encoding='utf-8')
            with patch.object(client.shutil, 'which', return_value='fake-tool'):
                result, _ = client.run(identity_file=key, output=Path(directory) / 'output',
                                       runner=fake, expected_boot=remote_report['boot_id'],
                                       expected_release=remote_report['release_id'])
        # Historical raw remains exportable but cannot attest the new driver.
        self.assertEqual(result['status'], 'NEEDS_REVIEW')
        self.assertIn('DRIVER_IDENTITY_MISMATCH', result['issues'])
        self.assertEqual(result['scan_frames_verified'], 105)
        self.assertEqual(len(result['files']), len(client.FILES))

    def test_transferred_script_hash_failure_never_starts_trial(self):
        calls = []

        def fake(command, **_kwargs):
            calls.append(command)
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 0, b'', b'')
            return subprocess.CompletedProcess(command, 0, b'bad-hash  file\n', b'')

        with tempfile.TemporaryDirectory(dir=client.ROOT / 'artifacts') as directory:
            key = Path(directory) / 'test-key'
            key.write_text('not a private key', encoding='utf-8')
            with patch.object(client.shutil, 'which', return_value='fake-tool'):
                result, _ = client.run(identity_file=key, output=Path(directory) / 'output',
                                       runner=fake, expected_boot='b', expected_release='r')
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('HASH_MISMATCH', result['reason'])

    def test_remote_report_path_outside_fixed_reports_is_rejected(self):
        calls = []

        def fake(command, **_kwargs):
            calls.append(command)
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 0, b'', b'')
            if len(calls) == 2:
                return subprocess.CompletedProcess(command, 0,
                                                   (client._sha(client.ROOT / 'scripts/robot_ros_scan_trial.py')
                                                    + '  script.py\n').encode(), b'')
            return subprocess.CompletedProcess(command, 2,
                b'{"schema_version":"twinpulse-ros-scan-trial-1.0","motion_authorized":false,'
                b'"report_directory":"/etc/ros-scan-20260930T000000Z-12345678"}\n', b'')

        with tempfile.TemporaryDirectory(dir=client.ROOT / 'artifacts') as directory:
            key = Path(directory) / 'test-key'
            key.write_text('not a private key', encoding='utf-8')
            with patch.object(client.shutil, 'which', return_value='fake-tool'):
                result, _ = client.run(identity_file=key, output=Path(directory) / 'output',
                                       runner=fake, expected_boot='b', expected_release='r')
        self.assertEqual(len(calls), 3)
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('IDENTITY_INVALID', result['reason'])


if __name__ == '__main__':
    unittest.main()
