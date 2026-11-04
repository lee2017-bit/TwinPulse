# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary start-path checks on Linux: role-based package check, Isaac
folder search, PowerShell-free start entries and the pure build checks.

No frozen EXE, Windows, Isaac, build or installed App run is involved."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
import build_windows_exe as build
import twinpulse_bootstrap_integrity as integrity
from twinpulse_app import simulation_assets
from twinpulse_app.release_contract import DATA_CONTRACT
from twinpulse_app.windows_install import install_package, rollback_package
entry=runpy.run_path(str(ROOT/'scripts/twinpulse_desktop_entry.py'))


def write_package(root,build_id,**fields):
    rows=[]
    for name in ('TwinPulse.exe','_internal/resources/scripts/twinpulse_backend.py'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);data=(build_id+name).encode();path.write_bytes(data)
        rows.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    manifest=dict(schema='twinpulse-windows-exe-1.0',build_id=build_id,source_manifest_sha256=hashlib.sha256(build_id.encode()).hexdigest(),
        capabilities=dict(simulation=True,physical_robot=False,robot_observation=False),files=rows,**fields)
    (root/'windows-release-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return manifest


class StartPathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        environment=patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'profile')});environment.start();self.addCleanup(environment.stop)

    def test_internal_role_child_reads_only_the_manifest_and_other_starts_check_files(self):
        package=self.root/'package';manifest=write_package(package,'build_1')
        (package/'_internal/resources/scripts/twinpulse_backend.py').unlink()
        for arguments in (['--internal-role','backend'],['--internal-role','library-tool']):
            self.assertEqual(entry['check_package'](arguments,package),manifest)
        for arguments in ([],['--automation-test'],['--install'],['--install','--quiet'],['--inspect-package'],
                          ['--ready-timeout-s','600']):
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_FILE_MISMATCH: _internal/resources/scripts/twinpulse_backend\.py$'):
                entry['check_package'](arguments,package)
        # Capabilities are still normalized from the manifest the child read.
        environment={'TWINPULSE_ROBOT_OBSERVATION':'1'}
        entry['apply_packaged_capabilities'](entry['check_package'](['--internal-role','backend'],package),'backend',environment)
        self.assertEqual((environment['TWINPULSE_SIM_ONLY'],environment['TWINPULSE_RELEASE_ID']),('1','build_1'))
        self.assertNotIn('TWINPULSE_ROBOT_OBSERVATION',environment)
        (package/'windows-release-manifest.json').write_text(json.dumps(dict(manifest,schema='other')))
        with self.assertRaisesRegex(ValueError,'^WINDOWS_MANIFEST_INVALID$'):
            entry['check_package'](['--internal-role','backend'],package)

    def test_start_checks_do_not_hash_but_install_and_inspect_do(self):
        package=self.root/'package';write_package(package,'build_1')
        with patch.object(integrity,'sha256',side_effect=AssertionError('hashed')):
            for arguments in ([],['--internal-role','backend'],['--automation-test'],['--ready-timeout-s','600']):
                self.assertEqual(entry['check_package'](arguments,package)['build_id'],'build_1')
            for arguments in (['--install'],['--install','--quiet'],['--inspect-package']):
                with self.assertRaisesRegex(AssertionError,'hashed'):entry['check_package'](arguments,package)

    def test_same_size_change_passes_a_start_but_stops_install_before_its_code_runs(self):
        package=self.root/'package';write_package(package,'build_1')
        script=package/'_internal/resources/scripts/twinpulse_backend.py'
        data=script.read_bytes();script.write_bytes(data[:-1]+bytes([data[-1]^1]))
        self.assertEqual(entry['check_package']([],package)['build_id'],'build_1')
        for arguments in (['--install'],['--install','--quiet'],['--inspect-package']):
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_FILE_MISMATCH: _internal/resources/scripts/twinpulse_backend\.py$'):
                entry['check_package'](arguments,package)

    def test_startup_failure_dialog_names_the_launcher_error_and_its_log(self):
        text=entry['startup_failure_text'];log=self.root/'profile/TwinPulse/runtime/desktop-logs/launcher-42.log'
        message='Isaac did not finish starting within 600 s (last phase: extensions, started at 412 s)'
        self.assertEqual(text({'code':'engine_ready_timeout','message':message},log).splitlines(),
            ['TwinPulse could not complete startup.',message,'Code: engine_ready_timeout','Log: '+str(log),
             'No other application was stopped.'])
        # Without a reported error (for example the App closed after running) the dialog points to diagnostics.
        self.assertEqual(text({},None).splitlines()[1:3],
            ['Open the diagnostics if the App is visible.',r'Log: %LOCALAPPDATA%\TwinPulse\runtime\desktop-logs'])

    def test_isaac_search_tries_saved_folder_then_usual_installs_in_order(self):
        self.assertEqual(entry['ISAAC_CANDIDATES'],(r'C:\isaacsim',r'D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64',
            r'C:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64',r'D:\isaacsim'))
        find=entry['find_isaac_root'];folders=[self.root/name for name in ('saved','c','d-601','c-601','d')]
        for folder in folders:folder.mkdir()
        candidates=[str(folder) for folder in folders[1:]]
        self.assertIsNone(find(None,candidates))
        (folders[4]/'python.bat').write_text('');self.assertEqual(find(None,candidates),str(folders[4]))
        (folders[2]/'python.bat').write_text('');self.assertEqual(find(str(folders[0]),candidates),str(folders[2]))
        (folders[0]/'python.bat').write_text('');self.assertEqual(find(str(folders[0]),candidates),str(folders[0]))
        self.assertEqual(find('',candidates),str(folders[2]))
        # An unreadable probe (locked or offline drive) is skipped, so the folder dialog stays the fallback.
        stat=os.stat
        def locked(path,*arguments,**options):
            if 'locked' in str(path):raise PermissionError(13,'Access is denied',str(path))
            return stat(path,*arguments,**options)
        with patch('os.stat',side_effect=locked):
            self.assertEqual(find(str(self.root/'locked'),[str(self.root/'locked-d'),str(folders[2])]),str(folders[2]))
            self.assertIsNone(find(None,[str(self.root/'locked-d')]))

    def test_installed_start_entries_run_the_active_exe_without_powershell(self):
        installed=self.root/'installed'
        for build_id in ('build_1','build_2'):
            source=self.root/build_id;write_package(source,build_id,data_contract=DATA_CONTRACT)
            install_package(source,installed)
        expected={'Start-TwinPulse.cmd':b'@echo off\r\nstart "" "%~dp0releases\\build_2\\TwinPulse.exe" %*\r\n',
                  'Start-TwinPulse-Test.cmd':b'@echo off\r\nstart "" "%~dp0releases\\build_2\\TwinPulse.exe" --automation-test %*\r\n'}
        for name,content in expected.items():
            self.assertEqual((installed/name).read_bytes(),content)
        self.assertTrue((installed/'releases/build_2/TwinPulse.exe').is_file())
        self.assertIn('active-release.json',(installed/'start-installed.ps1').read_text(encoding='utf-8'))
        # Rollback rewrites the entries, so they keep following the active pointer.
        rollback_package(installed,'build_1')
        self.assertEqual(json.loads((installed/'active-release.json').read_bytes())['release_id'],'build_1')
        self.assertEqual((installed/'Start-TwinPulse.cmd').read_bytes(),expected['Start-TwinPulse.cmd'].replace(b'build_2',b'build_1'))
        self.assertEqual((installed/'Start-TwinPulse-Test.cmd').read_bytes(),
                         expected['Start-TwinPulse-Test.cmd'].replace(b'build_2',b'build_1'))

    def test_build_requires_public_burger_bytes_and_names_the_differences(self):
        assets=ROOT/'assets/simulation/turtlebot3_burger/usd'
        self.assertEqual(build.burger_asset_check(assets),simulation_assets.PUBLIC_BURGER_MANIFEST)
        changed=dict(simulation_assets.PUBLIC_BURGER_MANIFEST,**{'payloads/robot.usda':'0'*64,'payloads/base.usda':'1'*64})
        with patch.object(simulation_assets,'_inventory',return_value=changed):
            with self.assertRaisesRegex(ValueError,r'^BUILD_BURGER_ASSET_NOT_PUBLIC: payloads/base\.usda, payloads/robot\.usda$'):
                build.burger_asset_check(assets)
        copy=self.root/'usd';shutil.copytree(assets,copy)
        (copy/'payloads/base.usda').write_bytes((copy/'payloads/base.usda').read_bytes()+b'\n')
        with self.assertRaises(ValueError):build.burger_asset_check(copy)
        (copy/'payloads/base.usda').unlink()
        with self.assertRaises(ValueError):build.burger_asset_check(copy)

    def test_install_path_check_lists_five_longest_and_fails_only_past_max_path(self):
        # A real build id (29 characters) gives a 103-character installed prefix with a 20-character user name.
        release='20261103T000000Z-0123456789ab';fits='_internal/resources/'+'a'*(259-103-20)
        names=['TwinPulse.exe','LICENSE','desktop/locales/en-US.pak','_internal/python312.dll','README.md','NOTICE',fits]
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(build.install_path_check(names,release),(259,fits))
        self.assertEqual(printed.getvalue().splitlines()[1:],['  259 (156 relative) '+fits,
            '  128 (25 relative) desktop/locales/en-US.pak','  126 (23 relative) _internal/python312.dll',
            '  116 (13 relative) TwinPulse.exe','  112 (9 relative) README.md'])
        with redirect_stdout(io.StringIO()) as printed,self.assertRaisesRegex(ValueError,'^BUILD_INSTALL_PATH_TOO_LONG: 260 > 259: '+fits+'b$'):
            build.install_path_check(names+[fits+'b'],release)
        self.assertIn('  260 (157 relative) '+fits+'b',printed.getvalue())
        # The builder-only override keeps the warning and builds.
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(build.install_path_check(names+[fits+'b'],release,allow_long=True),(260,fits+'b'))
        self.assertIn('WARNING BUILD_INSTALL_PATH_TOO_LONG: 260 > 259: '+fits+'b',printed.getvalue())


if __name__=='__main__':unittest.main()
