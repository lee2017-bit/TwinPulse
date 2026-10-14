# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free deployment/lease tests. Never open robot serial or start ROS."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime as r


class RuntimeTests(unittest.TestCase):
    def test_stationary_operation_log_exists_even_without_logged_subprocess(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = r.create_operation_log(root)
            self.assertEqual(log.name, 'operation.log')
            self.assertEqual(log.read_bytes(), b'')
            with self.assertRaises(FileExistsError):
                r.create_operation_log(root)

    def test_mismatched_imported_params_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);source = root / 'source';source.mkdir()
            guard = root / 'guard';guard.write_text('qualified fixture')
            params = root / 'params.yaml';params.write_text('modified params')
            profile = {'architecture':'aarch64','guard_sha256':r.digest(guard),
                       'import_guard':str(guard),'import_params':str(params),
                       'import_params_sha256':'0'*64}
            (source / 'profile.json').write_text(json.dumps(profile))
            home = root / 'deployment';home.mkdir()
            with patch.object(r.platform,'machine',return_value='aarch64'), \
                 patch.object(r.Path,'home',return_value=Path('/home/twinpulse')), \
                 patch.object(r,'run_logged') as build:
                with self.assertRaisesRegex(ValueError,'IMPORTED_PARAMS_DIGEST_MISMATCH'):
                    r.prepare(source,home,root / 'log')
                build.assert_not_called()
                self.assertFalse((home / 'current').exists())

    def test_ros_argument_preflight_failure_prevents_release_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);source = root / 'source';source.mkdir()
            guard = root / 'guard';guard.write_text('qualified fixture')
            params = root / 'params.yaml';params.write_text('reviewed params')
            (source / 'profile.json').write_text(json.dumps({
                'architecture':'aarch64','guard_sha256':r.digest(guard),
                'import_guard':str(guard),'import_params':str(params),
                'import_params_sha256':r.digest(params)}))
            home=root / 'deployment';home.mkdir()
            with patch.object(r.platform,'machine',return_value='aarch64'), \
                 patch.object(r.Path,'home',return_value=Path('/home/twinpulse')), \
                 patch.object(r,'run_logged',side_effect=RuntimeError('ROS arguments rejected')) as run:
                with self.assertRaisesRegex(RuntimeError,'ROS arguments rejected'):
                    r.prepare(source,home,root / 'log')
                self.assertEqual(run.call_count,1)
                self.assertEqual(run.call_args.args[0][:2],['/bin/bash',str(source / 'ros_preflight.sh')])
                self.assertFalse((home / 'current').exists())

    def fixture(self, root):
        (root / 'bin').mkdir()
        for name in ['runtime.py', 'robot_health.py', 'bin/opencr_readonly', 'bin/turtlebot3_ros', 'burger.yaml',
                     'stationary.py', 'stationary.sh', 'stationary_observer.py', 'owned_exec.py']:
            (root / name).write_text('fixture')
        (root / 'profile.json').write_text(json.dumps({'guard_sha256': r.digest(root / 'bin/turtlebot3_ros')}))
        manifest = {'schema_version': 'robot-release-1.0', 'profile': 'twinpulse-burger',
                    'source_id': 'a' * 64, 'motion_enabled': False, 'files': {p.relative_to(root).as_posix(): r.digest(p)
                                                     for p in root.rglob('*') if p.is_file()}}
        r.write_json(root / 'manifest.json', manifest)
        return manifest

    def test_manifest_changed_missing_and_motion_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.fixture(root)
            r.verify_release(root)
            (root / 'bin/opencr_readonly').write_text('changed')
            with self.assertRaises(ValueError):
                r.verify_release(root)
            (root / 'bin/opencr_readonly').unlink()
            with self.assertRaises(OSError):
                r.verify_release(root)
            manifest['motion_enabled'] = True
            r.write_json(root / 'manifest.json', manifest)
            with self.assertRaises(ValueError):
                r.verify_release(root)

    def test_manifest_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.fixture(root)
            manifest['files']['../outside'] = 'x'
            r.write_json(root / 'manifest.json', manifest)
            with self.assertRaises(ValueError):
                r.verify_release(root)

    def test_busy_unknown_and_idle(self):
        for code, err in [(0, b''), (2, b'failure'), (1, b'permission denied')]:
            with patch.object(r.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, b'', err)):
                with self.assertRaises(RuntimeError):
                    r.idle_port()
        with patch.object(r.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'')):
            r.idle_port()

    def test_off_requires_explicit_confirmation_verified_helper_and_idle_port(self):
        root = Path('/fixture')
        with patch.object(r, 'verify_release') as verify, patch.object(r, 'idle_port') as idle, \
             patch.object(r, 'run_logged') as run:
            with self.assertRaises(ValueError):
                r.disarm_board(root, root / 'log', 9)
            verify.assert_not_called()
            verify.return_value = {'files': {}}
            with self.assertRaises(ValueError):
                r.disarm_board(root, root / 'log', 9, True)
            run.assert_not_called()
            verify.return_value = {'files': {'bin/opencr_torque_off': 'fixture'}}
            idle.side_effect = RuntimeError('BUSY')
            with self.assertRaises(RuntimeError):
                r.disarm_board(root, root / 'log', 9, True)
            run.assert_not_called()
            idle.side_effect = None
            r.disarm_board(root, root / 'log', 9, True)
            command = run.call_args.args[0]
            self.assertEqual(command[3], 'torque-off')
            self.assertEqual(run.call_args.kwargs, {'timeout': 8, 'pass_fds': (9,)})
            run.assert_called_once()

    def test_invalid_off_flags_fail_before_any_robot_access(self):
        for flags in [('read-board', '--disable-torque', '--operator-confirmed-flat-clear-floor'),
                      ('prepare', '--disable-torque'),
                      ('prepare', '--operator-confirmed-flat-clear-floor')]:
            result = subprocess.run([sys.executable, '-B', str(Path(r.__file__)), *flags],
                                    capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stderr.decode(errors='replace'))
            self.assertIn(b'OFF requires', result.stderr)

    def test_prepare_cache_changed_artifact_and_interrupted_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            source.mkdir()
            for name in ['runtime.py', 'robot_health.py', 'stationary.py', 'stationary.sh', 'stationary_observer.py', 'owned_exec.py']:
                (source / name).write_text('fixture')
            imported = root / 'qualified-guard'
            imported.write_text('qualified fixture')
            params = root / 'params.yaml'
            params.write_text('fixture params')
            profile = {'architecture': 'aarch64', 'guard_sha256': r.digest(imported),
                       'import_guard': str(imported), 'import_params': str(params),
                       'import_params_sha256': r.digest(params), 'vendor_commit': 'fixed'}
            (source / 'profile.json').write_text(json.dumps(profile))
            home = root / 'deployment'
            home.mkdir()

            def fake_build(command, log, timeout=120):
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_text('fixture binary')

            with patch.object(r.platform, 'machine', return_value='aarch64'), \
                 patch.object(r.Path, 'home', return_value=Path('/home/twinpulse')), \
                 patch.object(r, 'run_logged', side_effect=fake_build) as run:
                release, cached = r.prepare(source, home, root / 'log')
                self.assertFalse(cached)
                self.assertEqual((home / 'current').resolve(), release)
                r.verify_release(release)
                run.reset_mock()
                second, cached = r.prepare(source, home, root / 'log')
                self.assertEqual(second, release)
                self.assertTrue(cached)
                run.assert_not_called()
                (release / 'bin/opencr_readonly').write_text('changed')
                with self.assertRaises(ValueError):
                    r.prepare(source, home, root / 'log')
                run.assert_not_called()
                # New source failure must never replace the existing current pointer.
                (source / 'runtime.py').write_text('changed source')
                run.side_effect = RuntimeError('build interrupted')
                with self.assertRaises(RuntimeError):
                    r.prepare(source, home, root / 'log')
                self.assertEqual((home / 'current').resolve(), release)

                # Driver dependency failure must not select a newly built release.
                (source / 'isolated_ros_scan.py').write_text('fixture adapter')
                (source / 'coin_driver_identity.py').write_text('fixture identity')

                def reject_driver(command, log, timeout=120):
                    if '--artifact-preflight' in command:
                        raise RuntimeError('ISOLATED_DRIVER_LIBRARY_UNRESOLVED')
                    fake_build(command, log, timeout)

                run.side_effect = reject_driver
                with self.assertRaisesRegex(RuntimeError, 'ISOLATED_DRIVER_LIBRARY_UNRESOLVED'):
                    r.prepare(source, home, root / 'log')
                self.assertEqual((home / 'current').resolve(), release)
                run.side_effect = fake_build
                selected, cached = r.prepare(source, home, root / 'log')
                self.assertTrue(cached)  # Built version was preserved, not selected on failure.
                self.assertEqual((home / 'current').resolve(), selected)
                run.reset_mock()
                run.side_effect = reject_driver
                with self.assertRaisesRegex(RuntimeError, 'ISOLATED_DRIVER_LIBRARY_UNRESOLVED'):
                    r.prepare(source, home, root / 'log')
                run.assert_called_once()
                self.assertIn('--artifact-preflight', run.call_args.args[0])
                self.assertEqual((home / 'current').resolve(), selected)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux flock')
    def test_lease_busy_and_release_on_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with r.ownership(home):
                with self.assertRaisesRegex(RuntimeError, 'BUSY'):
                    with r.ownership(home):
                        self.fail('second owner entered')
            try:
                with r.ownership(home):
                    raise ValueError('interrupted operation')
            except ValueError:
                pass
            with r.ownership(home):
                self.assertTrue((home / 'state/opencr.lock').is_file())

    @unittest.skipUnless(sys.platform == 'linux', 'Linux process groups')
    def test_child_timeout_reaped_before_lease_released(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            child = root / 'fixture.py'
            child.write_text('import os,time,pathlib\npathlib.Path(__file__).with_suffix(".pid").write_text(str(os.getpid()))\ntime.sleep(20)\n')
            with r.ownership(root):
                with self.assertRaises(subprocess.TimeoutExpired):
                    r.run_logged([sys.executable, str(child)], root / 'log', timeout=1)
                pid = int(child.with_suffix('.pid').read_text())
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
            with r.ownership(root):
                pass


if __name__ == '__main__':
    unittest.main()
