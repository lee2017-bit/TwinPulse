# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The frozen Windows entry driven on Linux: what an error writes and shows,
and which Isaac folder a start uses and saves.

Supplementary. sys.frozen, sys._MEIPASS and ctypes.windll are patched
(create=True) and a stub file stands in for the bundled launcher, so no EXE,
Windows, Isaac or real launch is involved. The package check is the real one,
run on a small package folder."""
from contextlib import redirect_stderr, redirect_stdout
import ctypes
import hashlib
import io
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
from twinpulse_app import ProcessManagerError  # noqa: E402
from twinpulse_app.desktop_settings import read_settings, save_settings  # noqa: E402

ENTRY = runpy.run_path(str(ROOT / 'scripts/twinpulse_desktop_entry.py'))
BACKEND = '_internal/resources/scripts/twinpulse_backend.py'
PID = str(os.getpid())
# Stands in for the bundled launcher and keeps the arguments the entry gave it.
RECORDING_LAUNCHER = ('import json\nimport sys\nfrom pathlib import Path\n\n\ndef main():\n'
                      '    Path(__file__).with_name("argv.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")\n'
                      '    return 0\n')


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

    def test_launcher_failure_text_reads_the_real_launcher_globals_after_a_failed_main(self):
        # The same access as main(): runpy returns a copy of the launcher's globals.
        launcher = runpy.run_path(str(ROOT / 'scripts/twinpulse_launcher.py'))
        main = launcher['main']
        message = 'Isaac did not finish starting within 600 s (last phase: extension_enable, last reported at 412 s)'

        def refuse(**_options):
            raise ProcessManagerError('engine_ready_timeout', message)
        argv = ['twinpulse_launcher.py', '--no-browser', '--state-dir', str(self.root / 'state'),
                '--isaac-root', str(self.root / 'isaac')]
        with patch.dict(main.__globals__, {'TwinPulseProcessManager': refuse, '_browser': lambda configured: None}), \
                patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(), 1)
        self.assertTrue(err.getvalue().startswith('TWINPULSE_LAUNCH_ERROR code=engine_ready_timeout message='))
        log = self.logs / 'launcher-42.log'
        self.assertEqual(ENTRY['launcher_failure_text'](launcher, log).splitlines(),
                         ['TwinPulse could not complete startup.', message, 'Code: engine_ready_timeout',
                          'Log: ' + str(log), 'No other application was stopped.'])

    def test_failed_launcher_dialog_gets_the_launcher_globals_and_this_runs_log(self):
        launcher_file = self.scripts / 'twinpulse_launcher.py'
        launcher_file.write_text('LAST_LAUNCH_ERROR = {}\n\n\ndef main():\n    LAST_LAUNCH_ERROR.update('
                                 'code="engine_ready_timeout", message="Isaac did not finish starting")\n    return 1\n',
                                 encoding='utf-8')
        real, calls = ENTRY['launcher_failure_text'], []

        def spy(launcher_globals, log_path):
            calls.append((launcher_globals, log_path))
            return real(launcher_globals, log_path)
        code, box = self.run_frozen('--isaac-root', str(self.root / 'isaac'), entry_globals={'launcher_failure_text': spy})
        log = self.logs / ('launcher-' + PID + '.log')
        self.assertEqual((code, len(calls)), (1, 1))
        launcher_globals, log_path = calls[0]
        self.assertEqual((launcher_globals['__file__'], launcher_globals['LAST_LAUNCH_ERROR'], log_path),
                         (str(launcher_file), {'code': 'engine_ready_timeout', 'message': 'Isaac did not finish starting'}, log))
        box.assert_called_once_with(None, '\n'.join(('TwinPulse could not complete startup.', 'Isaac did not finish starting',
                                    'Code: engine_ready_timeout', 'Log: ' + str(log), 'No other application was stopped.')),
                                    'TwinPulse startup', 0x10)

    def isaac_folder(self, name, version):
        folder = self.root / name
        folder.mkdir()
        (folder / 'python.bat').write_text('')
        if version is not None:
            (folder / 'VERSION').write_text(version + '\n', encoding='utf-8')
        return folder

    def launcher_arguments(self):
        recorded = self.scripts / 'argv.json'
        try:
            return json.loads(recorded.read_text(encoding='utf-8'))
        finally:
            recorded.unlink()

    def test_saved_isaac_folder_unreachable_now_keeps_the_setting_and_this_launch_uses_the_fallback(self):
        (self.scripts / 'twinpulse_launcher.py').write_text(RECORDING_LAUNCHER, encoding='utf-8')
        state = self.profile / 'TwinPulse' / 'runtime'
        saved = self.root / 'offline-drive' / 'isaacsim'  # like a D: drive that is not ready at this login
        fallback = self.isaac_folder('c-isaacsim', '5.1.0-rc.19+release.27451.a3bc6fd7.gl')
        save_settings(state, isaac_root=str(saved))
        settings = (state / 'desktop-settings.json').read_bytes()
        candidates = {'ISAAC_CANDIDATES': (str(self.root / 'missing'), str(fallback))}
        code, box = self.run_frozen(entry_globals=candidates)
        self.assertEqual((code, box.call_count), (0, 0))
        self.assertEqual(self.launcher_arguments(), ['--isaac-root', str(fallback)])
        self.assertEqual((state / 'desktop-settings.json').read_bytes(), settings)
        log = self.logs / ('launcher-' + PID + '.log')
        self.assertEqual([line for line in log.read_text(encoding='utf-8').splitlines() if 'ISAAC' in line],
                         ['TWINPULSE_ISAAC_ROOT_FALLBACK saved="' + str(saved) + '" used="' + str(fallback) + '" (no python.bat '
                          'in the saved folder now; used for this launch only, the setting is kept)'])
        # Once the saved folder is back, the next start uses it again.
        saved.mkdir(parents=True)
        (saved / 'python.bat').write_text('')
        code, box = self.run_frozen(entry_globals=candidates)
        self.assertEqual((code, self.launcher_arguments()), (0, []))
        self.assertEqual((state / 'desktop-settings.json').read_bytes(), settings)
        self.assertEqual(log.read_text(encoding='utf-8').count('TWINPULSE_ISAAC_ROOT_FALLBACK'), 1)

    def test_with_nothing_saved_a_6_0_1_folder_beats_an_earlier_other_version_and_is_saved(self):
        (self.scripts / 'twinpulse_launcher.py').write_text(RECORDING_LAUNCHER, encoding='utf-8')
        older = self.isaac_folder('c-isaacsim', '5.1.0-rc.19+release.27451.a3bc6fd7.gl')
        unknown = self.isaac_folder('c-isaacsim-no-version', None)
        release = self.isaac_folder('d-isaacsim-601', '6.0.1-rc.7+release.42383.32955d8d.gl')
        code, box = self.run_frozen(entry_globals={'ISAAC_CANDIDATES': (str(older), str(unknown), str(release))})
        self.assertEqual((code, box.call_count), (0, 0))
        self.assertEqual(read_settings(self.profile / 'TwinPulse' / 'runtime').get('isaac_root'), str(release))
        self.assertEqual(self.launcher_arguments(), [])
        self.assertNotIn('TWINPULSE_ISAAC_ROOT_FALLBACK', (self.logs / ('launcher-' + PID + '.log')).read_text(encoding='utf-8'))

    def test_a_folder_picked_in_the_dialog_is_saved_even_over_an_unreachable_saved_one(self):
        (self.scripts / 'twinpulse_launcher.py').write_text(RECORDING_LAUNCHER, encoding='utf-8')
        state = self.profile / 'TwinPulse' / 'runtime'
        save_settings(state, isaac_root=str(self.root / 'offline-drive' / 'isaacsim'))
        picked = self.isaac_folder('picked', None)
        tkinter = MagicMock()
        tkinter.filedialog.askdirectory.return_value = str(picked)
        with patch.dict(sys.modules, {'tkinter': tkinter, 'tkinter.filedialog': tkinter.filedialog}):
            code, box = self.run_frozen(entry_globals={'ISAAC_CANDIDATES': (str(self.root / 'missing'),)})
        self.assertEqual((code, box.call_count, tkinter.filedialog.askdirectory.call_count), (0, 0, 1))
        self.assertEqual(read_settings(state)['isaac_root'], str(picked.resolve()))
        self.assertEqual(self.launcher_arguments(), [])


if __name__ == '__main__':
    unittest.main()
