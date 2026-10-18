# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline preparation transport/bundle contracts; never connects to the robot."""
import json
import subprocess
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_robot as p
from raw_ros_record import RawRosRecorder


class PreparationTests(unittest.TestCase):
    def test_stationary_unsafe_receipt_path_stops_before_transfer(self):
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'robot-evidence'
            destination.mkdir()
            (destination/'export.json').mkdir()
            with self.assertRaisesRegex(ValueError,'EVIDENCE_RECEIPT_PATH_UNSAFE'):
                p.export_stationary_files({'run_id':'20260930T010203Z-1234abcd'},Path(folder),
                    scp='scp',options=[],target='fixture',
                    runner=lambda *_a,**_k:self.fail('transport called'))

    def test_stationary_unsafe_partial_is_explicit_and_not_transferred(self):
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'robot-evidence'
            destination.mkdir()
            (destination/'observer.log.part').mkdir()
            calls=[]
            def transfer(command,**_):
                calls.append(Path(command[-1]).name)
                return subprocess.CompletedProcess(command,1,b'',b'missing fixture')
            receipt=p.export_stationary_files({'run_id':'20260930T010203Z-1234abcd'},Path(folder),
                scp='scp',options=[],target='fixture',runner=transfer)
            self.assertEqual(receipt['status'],'INCOMPLETE')
            self.assertEqual(receipt['files']['observer.log']['status'],'LOCAL_PATH_UNSAFE_OR_STALE')
            self.assertNotIn('observer.log.part',calls)
            self.assertTrue((destination/'observer.log.part').is_dir())

    def test_stationary_transfer_resumes_only_missing_files_without_rerun(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            source.mkdir()
            raw = RawRosRecorder(source / 'ros-messages.raw', serializer=lambda value: value)
            self.assertTrue(raw.record('odom', b'whole-message'))
            footer = raw.close()
            run_id = '20260930T010203Z-1234abcd'
            (source / 'report.json').write_text(json.dumps({
                'run_id': run_id, 'boot_id': 'boot-a', 'release_id': 'release-a',
            }), encoding='utf-8')
            (source / 'telemetry.json').write_text(json.dumps({'raw_ros': footer}), encoding='utf-8')
            for name in p.STATIONARY_FILES:
                if not (source / name).exists():
                    (source / name).write_text(name, encoding='utf-8')
            calls = []
            fail_observer = [True]
            def fake_transfer(command, **_):
                name = Path(command[-1]).name.removesuffix('.part')
                calls.append(name)
                if name == 'observer.log' and fail_observer[0]:
                    return subprocess.CompletedProcess(command, 1, b'', b'missing')
                Path(command[-1]).write_bytes((source / name).read_bytes())
                return subprocess.CompletedProcess(command, 0, b'', b'')
            args = {'scp': 'scp', 'options': ['-o', 'BatchMode=yes'],
                    'target': 'twinpulse@192.168.35.139', 'runner': fake_transfer}
            expected = {'run_id': run_id, 'boot_id': 'boot-a', 'release_id': 'release-a'}
            first = p.export_stationary_files(expected, root / 'out', **args)
            self.assertEqual(first['status'], 'INCOMPLETE')
            self.assertEqual(first['raw_replay']['status'], 'VERIFIED_OFFLINE')
            fail_observer[0] = False
            calls.clear()
            (root/'out/robot-evidence/observer.log.part').write_text('interrupted fixture')
            second = p.export_stationary_files(expected, root / 'out', **args)
            self.assertEqual(calls, ['observer.log'])
            self.assertEqual(second['status'], 'COMPLETE')
            self.assertTrue(second['files']['observer.log']['stale_partial_discarded'])
            self.assertFalse((root/'out/robot-evidence/observer.log.part').exists())
            mismatched = p.export_stationary_files(
                {**expected, 'boot_id': 'boot-other'}, root / 'out', **args)
            self.assertEqual(mismatched['status'], 'INCOMPLETE')
            self.assertEqual(mismatched['report_binding']['status'], 'REJECTED')

    def test_stationary_export_collects_allowlisted_files_and_marks_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            def fake_transfer(command, **_):
                calls.append(command)
                name = Path(command[-1]).name.removesuffix('.part')
                if name != 'observer.log':
                    Path(command[-1]).write_bytes(name.encode())
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                return subprocess.CompletedProcess(command, 1, b'', b'missing')
            report = p.export_stationary_files(
                {'run_id': '20260930T010203Z-1234abcd'}, Path(folder), scp='scp',
                options=['-o', 'BatchMode=yes'], target='twinpulse@192.168.35.139',
                runner=fake_transfer)
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertEqual(report['files']['observer.log']['status'], 'MISSING_OR_TRANSFER_FAILED')
            self.assertEqual(report['files']['ros-messages.raw']['status'], 'COPIED')
            self.assertEqual(len(calls), len(p.STATIONARY_FILES))
            self.assertTrue((Path(folder) / 'robot-evidence/export.json').is_file())
            with self.assertRaises(ValueError):
                p.export_stationary_files({'run_id': '../../other'}, Path(folder), scp='scp',
                                          options=[], target='twinpulse@192.168.35.139',
                                          runner=fake_transfer)

    def test_saved_stationary_resume_is_transfer_only_and_requires_bound_report(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(p, 'ROOT', Path(folder)):
            client_id = '20260930T010203Z-1234abcd'
            saved = Path(folder) / 'artifacts/robot-preparation' / client_id / 'result/report.json'
            saved.parent.mkdir(parents=True)
            source = {'schema_version': 'robot-prepare-1.0',
                      'run_id': '20260930T010204Z-aabbccdd', 'action': 'stationary',
                      'motion_authorized': False, 'status': 'EVIDENCE_EXPORT_INCOMPLETE',
                      'boot_id': 'boot-a', 'release_id': 'release-a'}
            saved.write_text(json.dumps(source), encoding='utf-8')
            calls = []
            def fake_transfer(command, **_):
                calls.append(command)
                return subprocess.CompletedProcess(command, 1, b'', b'missing')
            receipt = p.resume_saved_stationary_export(
                saved, scp='scp', options=['-o', 'BatchMode=yes'],
                target='twinpulse@192.168.35.139', runner=fake_transfer)
            self.assertEqual(receipt['status'], 'INCOMPLETE')
            self.assertEqual(len(calls), len(p.STATIONARY_FILES))
            self.assertTrue(all(command[0] == 'scp' for command in calls))
            self.assertEqual(json.loads(saved.read_text(encoding='utf-8')), source)
            source['action'] = 'prepare'
            saved.write_text(json.dumps(source), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SAVED_STATIONARY_REPORT_INVALID'):
                p.resume_saved_stationary_export(saved, scp='scp', options=[],
                                                  target='twinpulse@192.168.35.139',
                                                  runner=fake_transfer)
            self.assertEqual(len(calls), len(p.STATIONARY_FILES))

    def test_resume_cli_never_starts_a_new_check_or_deployment(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(p, 'ROOT', Path(folder)):
            key = Path(folder) / 'existing-key'
            key.write_text('test fixture only', encoding='utf-8')
            saved = Path(folder) / 'artifacts/robot-preparation/20260930T010203Z-1234abcd/result/report.json'
            with patch.object(sys, 'argv', ['prepare', '--mode', 'resume-evidence',
                                           '--saved-report', str(saved), '--identity-file', str(key)]), \
                 patch.object(p.shutil, 'which', return_value='scp'), \
                 patch.object(p, 'resume_saved_stationary_export',
                              return_value={'status': 'COMPLETE'}) as transfer, \
                 patch.object(p.subprocess, 'run') as remote_command:
                self.assertEqual(p.main(), 0)
                remote_command.assert_not_called()
                transfer.assert_called_once()
            self.assertFalse(saved.parent.exists())

    def test_archive_reproducible_and_contains_sources_not_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / 'a.tar', Path(folder) / 'b.tar'
            self.assertEqual(p.bundle(a), p.bundle(b))
            with tarfile.open(a) as archive:
                names = archive.getnames()
                for name in ['src/opencr_readonly_check.cpp', 'trial/probe.cpp', 'robot_health.py',
                             'profile.json', 'runtime.py', 'stationary_observer.py', 'ros_observations.py',
                             'ros_preflight.py', 'ros_preflight.sh', 'raw_ros_record.py']:
                    self.assertIn(name, names)
                self.assertIn('src/opencr_torque_off.cpp', names)
                self.assertIn('include/twinpulse_robot_safety/torque_off.hpp', names)
                self.assertFalse(any('id_ed25519' in n or '..' in n or n.startswith('/') for n in names))

    def test_report_validation(self):
        data = {'schema_version': 'robot-prepare-1.0', 'motion_authorized': False, 'status': 'SOFTWARE_PREPARED_IDLE'}
        line = (p.MARKER + json.dumps(data)).encode()
        self.assertEqual(p.parse_prepare(line), data)
        for wrong in [b'no report', line + b'\n' + line]:
            with self.assertRaises(ValueError):
                p.parse_prepare(wrong)
        data['motion_authorized'] = True
        with self.assertRaises(ValueError):
            p.parse_prepare((p.MARKER + json.dumps(data)).encode())

    def test_offline_mode_has_no_transport_or_robot_access(self):
        # ROOT is redirected for outputs, not an empty substitute source tree.
        reviewed_inventory=p.bundle_files(p.ROOT)
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(p, 'ROOT', Path(folder)), \
             patch.object(p, 'bundle_files', return_value=reviewed_inventory), \
             patch.object(sys, 'argv', ['prepare', '--mode', 'offline']), \
             patch.object(p.subprocess, 'run') as transport:
            status = p.main()
            transport.assert_not_called()
            reports = list(Path(folder).rglob('report.json'))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertEqual(status, 0, report)
            self.assertEqual(report['status'], 'OFFLINE_BUNDLE_READY')
            self.assertFalse(report['motion_authorized'])

    def test_d1_does_not_offer_motion_entrypoint(self):
        profile = json.loads((p.PACKAGE / 'profile.json').read_text())
        self.assertFalse(profile['motion_enabled'])
        pinned = (p.ROOT / 'artifacts/robot-models/turtlebot3-source'
                  / 'turtlebot3_bringup/param/humble/burger.yaml')
        import hashlib
        self.assertEqual(len(profile['import_params_sha256']), 64)
        if pinned.is_file():
            # The retained checkout uses CRLF on Windows; the deployed Linux
            # vendor file uses LF. Pin the exact Linux bytes that runtime reads.
            linux_bytes = pinned.read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(linux_bytes).hexdigest(), profile['import_params_sha256'])
        text = (p.PACKAGE / 'runtime.py').read_text()
        self.assertIn("choices=['prepare', 'read-board', 'verify', 'stationary']", text)
        self.assertNotIn("'--run-once'", text)

    def test_off_flags_cannot_be_implicit_or_used_for_read_only_modes(self):
        for flags in [('--disable-torque',), ('--operator-confirmed-flat-clear-floor',),
                      ('--mode', 'offline', '--disable-torque', '--operator-confirmed-flat-clear-floor'),
                      ('--mode', 'stationary', '--disable-torque', '--operator-confirmed-flat-clear-floor')]:
            with patch.object(sys, 'argv', ['prepare', *flags]), \
                 patch.object(p.subprocess, 'run') as transport:
                with self.assertRaises(SystemExit) as error:
                    p.main()
                self.assertEqual(error.exception.code, 2)
                transport.assert_not_called()


if __name__ == '__main__':
    unittest.main()
