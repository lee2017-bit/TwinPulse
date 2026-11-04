# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The frozen Windows entry driven on Linux: what an error writes and shows.

Supplementary. sys.frozen, sys._MEIPASS and ctypes.windll are patched
(create=True) and a stub file stands in for the bundled launcher, so no EXE,
Windows, Isaac or real launch is involved. The package check is the real one,
run on a small package folder."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
ENTRY = runpy.run_path(str(ROOT / 'scripts/twinpulse_desktop_entry.py'))
BACKEND = '_internal/resources/scripts/twinpulse_backend.py'
PID = str(os.getpid())


def write_package(root):
    """A package folder for the real bootstrap check: a manifest and the two files it lists."""
    rows = []
    for name in ('TwinPulse.exe', BACKEND):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        rows.append(dict(path=name, bytes=len(name.encode()), sha256=hashlib.sha256(name.encode()).hexdigest()))
    (root / 'windows-release-manifest.json').write_text(json.dumps(dict(
        schema='twinpulse-windows-exe-1.0', build_id='build_1', product_version='0.0.0-test',
        capabilities=dict(simulation=True, physical_robot=False, robot_observation=False), files=rows)), encoding='utf-8')


class FrozenEntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT / 'artifacts' / 'test-tmp')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile = self.root / 'profile'
        self.logs = self.profile / 'TwinPulse' / 'runtime' / 'desktop-logs'
        self.package = self.root / 'package'
        write_package(self.package)
        self.scripts = self.root / 'bundle' / 'resources' / 'scripts'
        self.scripts.mkdir(parents=True)

    def run_frozen(self, *arguments, environment=None, entry_globals=None):
        """run_entry as TwinPulse.exe runs it; returns (exit code, MessageBoxW mock).

        LOCALAPPDATA and HOME are temp folders unless environment says
        otherwise (None removes a variable)."""
        windll = MagicMock()
        values = {'LOCALAPPDATA': str(self.profile), 'HOME': str(self.root / 'home'), **(environment or {})}
        out, err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = None  # as in a windowed bootloader
        try:
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, '_MEIPASS', str(self.root / 'bundle'), create=True), \
                    patch.object(sys, 'executable', str(self.package / 'TwinPulse.exe')), \
                    patch.object(sys, 'argv', ['TwinPulse.exe', *arguments]), \
                    patch.object(sys, 'path', list(sys.path)), \
                    patch.object(sys, 'dont_write_bytecode', sys.dont_write_bytecode), \
                    patch.object(ctypes, 'windll', windll, create=True), \
                    patch.dict(os.environ), patch.dict(ENTRY['main'].__globals__, entry_globals or {}):
                for key, value in values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                code = ENTRY['run_entry'](list(arguments))
        finally:
            # main() points both streams at its log file once it opens one.
            opened, sys.stdout, sys.stderr = sys.stdout, out, err
            if opened is not None:
                opened.close()
        return code, windll.user32.MessageBoxW

    def test_failure_before_the_log_is_open_writes_a_new_log_and_the_dialog_names_it(self):
        (self.package / BACKEND).unlink()
        error = 'ValueError: WINDOWS_PACKAGE_FILE_MISMATCH: ' + BACKEND
        for index, (arguments, first, role) in enumerate((((), 'TwinPulse could not start.', 'launcher'),
                (('--install',), 'TwinPulse could not be installed.', 'install'),
                (('--inspect-package',), 'TwinPulse package check failed.', 'launcher'))):
            with self.subTest(arguments=arguments):
                profile = self.root / ('profile-' + str(index))
                code, box = self.run_frozen(*arguments, environment={'LOCALAPPDATA': str(profile)})
                log = profile / 'TwinPulse' / 'runtime' / 'desktop-logs' / (role + '-' + PID + '.log')
                self.assertEqual(code, 1)
                self.assertEqual(list(log.parent.iterdir()), [log])
                text = log.read_text(encoding='utf-8')
                # The whole traceback of the bootstrap check that stopped the run.
                self.assertTrue(text.startswith('Traceback (most recent call last):\n'), text)
                self.assertIn('in verify_before_import', text)
                self.assertTrue(text.endswith('\n' + error + '\n'), text)
                box.assert_called_once_with(None, first + '\n' + error + '\nLog: ' + str(log), 'TwinPulse startup', 0x10)

    def test_quiet_install_and_internal_roles_log_the_failure_without_a_dialog(self):
        (self.package / BACKEND).unlink()
        code, box = self.run_frozen('--install', '--quiet')
        self.assertEqual((code, box.call_count), (1, 0))
        self.assertTrue((self.logs / ('install-' + PID + '.log')).read_text(encoding='utf-8')
                        .endswith('\nValueError: WINDOWS_PACKAGE_FILE_MISMATCH: ' + BACKEND + '\n'))
        # A child role only reads the manifest; an invalid one is logged under the child's role.
        manifest = self.package / 'windows-release-manifest.json'
        manifest.write_text(json.dumps(dict(json.loads(manifest.read_text(encoding='utf-8')), schema='other')), encoding='utf-8')
        code, box = self.run_frozen('--internal-role', 'backend')
        self.assertEqual((code, box.call_count), (1, 0))
        self.assertTrue((self.logs / ('backend-' + PID + '.log')).read_text(encoding='utf-8')
                        .endswith('\nValueError: WINDOWS_MANIFEST_INVALID\n'))
        # A role value that is not a plain name never becomes part of the log path.
        write_package(self.package)
        code, box = self.run_frozen('--internal-role', '../escaped')
        self.assertEqual((code, box.call_count), (1, 0))
        self.assertEqual(sorted(path.name for path in self.logs.iterdir()),
                         ['backend-' + PID + '.log', 'install-' + PID + '.log', 'internal-role-' + PID + '.log'])
        self.assertTrue((self.logs / ('internal-role-' + PID + '.log')).read_text(encoding='utf-8')
                        .endswith('\nValueError: UNSUPPORTED_DESKTOP_ROLE\n'))
        self.assertEqual([path for path in self.root.rglob('*') if 'escaped' in path.name], [])

    def test_without_localappdata_or_a_writable_folder_the_dialog_says_no_log_was_written(self):
        (self.package / BACKEND).unlink()
        blocked = self.root / 'blocked'
        blocked.write_bytes(b'')  # a file where the folder would be: every write below it fails
        for environment in ({'LOCALAPPDATA': None}, {'LOCALAPPDATA': str(blocked)}):
            with self.subTest(environment=environment):
                code, box = self.run_frozen(environment=environment)
                self.assertEqual(code, 1)
                box.assert_called_once_with(None, 'TwinPulse could not start.\nValueError: WINDOWS_PACKAGE_FILE_MISMATCH: '
                                            + BACKEND + '\nNo log was written.', 'TwinPulse startup', 0x10)
        self.assertEqual(list(self.root.rglob('*.log')), [])
        self.assertEqual(blocked.read_bytes(), b'')

    def test_failure_after_the_log_is_open_goes_to_that_log_only(self):
        (self.scripts / 'twinpulse_launcher.py').write_text('def main():\n    raise RuntimeError("stub launcher stopped")\n',
                                                            encoding='utf-8')
        code, box = self.run_frozen('--isaac-root', str(self.root / 'isaac'))
        log = self.logs / ('launcher-' + PID + '.log')
        self.assertEqual(code, 1)
        self.assertEqual(list(self.logs.iterdir()), [log])
        text = log.read_text(encoding='utf-8')
        self.assertEqual(text.count('Traceback (most recent call last):'), 1)
        self.assertTrue(text.endswith('\nRuntimeError: stub launcher stopped\n'), text)
        box.assert_called_once_with(None, 'TwinPulse could not start.\nRuntimeError: stub launcher stopped\nLog: ' + str(log),
                                    'TwinPulse startup', 0x10)


if __name__ == '__main__':
    unittest.main()
