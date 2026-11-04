# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary real-bind, package integrity and shutdown contract checks."""
from pathlib import Path
import hashlib
import json
import runpy
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
from twinpulse_app import CommandBroker, LocalApiServer
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.desktop_settings import read_settings, save_settings
from twinpulse_app.runtime_paths import resource_root, script_command
from twinpulse_app.windows_package import verify_package


class DesktopContractTests(unittest.TestCase):
    def test_every_frozen_role_uses_manifest_robot_capabilities(self):
        apply=runpy.run_path(str(ROOT/'scripts/twinpulse_desktop_entry.py'))['apply_packaged_capabilities']
        for role in ('launcher','backend','install'):
            environment={'TWINPULSE_ROBOT_OBSERVATION':'1'}
            apply({'capabilities':{'physical_robot':False}},role,environment)
            self.assertEqual(environment['TWINPULSE_SIM_ONLY'],'1')
            self.assertNotIn('TWINPULSE_ROBOT_OBSERVATION',environment)
        for role in ('robot-prepare','robot-readiness'):
            with self.assertRaisesRegex(ValueError,'PACKAGE_PHYSICAL_ROLE_DISABLED'):
                apply({'capabilities':{'physical_robot':False,'robot_observation':True}},role,{})
        environment={}
        apply({'capabilities':{'physical_robot':False,'robot_observation':True}},'backend',environment)
        self.assertEqual(environment['TWINPULSE_SIM_ONLY'],'1')
        self.assertEqual(environment['TWINPULSE_ROBOT_OBSERVATION'],'1')

    def test_quiet_install_failure_never_waits_for_a_native_error_dialog(self):
        entry=runpy.run_path(str(ROOT/'scripts/twinpulse_desktop_entry.py'))
        with patch.object(sys,'frozen',True,create=True):
            self.assertFalse(entry['should_show_error_dialog'](['--install','--quiet']))
            self.assertFalse(entry['should_show_error_dialog'](['--internal-role','backend']))
            self.assertTrue(entry['should_show_error_dialog'](['--install']))
            self.assertTrue(entry['should_show_error_dialog']([]))

    def test_remember_actual_bound_port_without_overwriting_isaac_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(read_settings(root)['preferred_port'], 8765)
            save_settings(root, isaac_root='C:/Existing Isaac', preferred_port=8766)
            save_settings(root, preferred_port=8767)
            self.assertEqual(read_settings(root)['isaac_root'], 'C:/Existing Isaac')
            self.assertEqual(read_settings(root)['preferred_port'], 8767)

    def test_real_bind_collision_keeps_other_listener_and_uses_next_candidate(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0)); occupied.listen()
            port = occupied.getsockname()[1]
            server = LocalApiServer(CommandBroker(project_id='default'),
                product_bootstrap_secret='p'*40, engine_bootstrap_secret='e'*40,
                port=port, port_candidates=10)
            try:
                self.assertNotEqual(server.port, port)
                self.assertLessEqual(server.port, port + 9)
                self.assertEqual(occupied.getsockname()[1], port)
            finally:
                server._httpd.server_close()

    def test_frozen_child_is_role_not_python_script_or_cwd(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', 'C:/Bundle', create=True):
            self.assertEqual(script_command(ROOT, 'backend'), [sys.executable, '--internal-role', 'backend'])
            self.assertEqual(resource_root(), Path('C:/Bundle').resolve() / 'resources')
            with self.assertRaises(ValueError): script_command(ROOT, '../arbitrary.py')

    def test_idle_shutdown_is_idempotent_and_pending_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); status=directory/'supervisor-status.json'; shutdown=directory/'shutdown.request'
            status.write_text(json.dumps({'status':'ready','phase':'ready'}))
            server=LocalApiServer(CommandBroker(project_id='default'), virtual=True,
                product_bootstrap_secret='p'*40, engine_bootstrap_secret='e'*40,
                supervisor_status_file=status, launcher_shutdown_file=shutdown)
            with patch.object(server.broker, 'has_pending_operations', return_value=True):
                self.assertFalse(server._supervisor_status()['shutdown_available'])
                with self.assertRaises(BrokerError): server._request_shutdown()
            self.assertTrue(server._supervisor_status()['shutdown_available'])
            first=server._request_shutdown()
            self.assertEqual(server._request_shutdown(), first)
            self.assertTrue(server._supervisor_status()['shutdown_requested'])

    def test_complete_package_manifest_rejects_changed_and_unlisted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); entry=root/'TwinPulse.exe'; entry.write_bytes(b'owned-test-placeholder')
            manifest={'schema':'twinpulse-windows-exe-1.0','build_id':'test',
                'source_manifest_sha256':'a'*64,'files':[{'path':entry.name,'bytes':entry.stat().st_size,
                'sha256':hashlib.sha256(entry.read_bytes()).hexdigest()}]}
            (root/'windows-release-manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(verify_package(root)['status'], 'verified')
            extra=root/'extra'; extra.write_bytes(b'extra')
            with self.assertRaises(ValueError): verify_package(root)
            extra.unlink(); entry.write_bytes(b'changed')
            with self.assertRaises(ValueError): verify_package(root)

    def test_package_check_tolerates_file_manager_junk_and_names_unexpected_files(self):
        # build_windows_exe and archive tools load the verifier standalone through runpy.
        standalone=runpy.run_path(str(ROOT/'packages/twinpulse_app/src/twinpulse_app/windows_package.py'))['verify_package']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); entry=root/'TwinPulse.exe'; entry.write_bytes(b'owned-test-placeholder')
            manifest={'schema':'twinpulse-windows-exe-1.0','build_id':'test','source_manifest_sha256':'a'*64,
                'files':[{'path':entry.name,'bytes':entry.stat().st_size,'sha256':hashlib.sha256(entry.read_bytes()).hexdigest()}]}
            (root/'windows-release-manifest.json').write_text('\ufeff'+json.dumps(manifest),encoding='utf-8')
            (root/'_internal').mkdir()
            for junk in ('Thumbs.db','desktop.ini','_internal/.DS_Store'):(root/junk).write_bytes(b'file-manager')
            for check in (verify_package,standalone):self.assertEqual(check(root)['files'],1)
            (root/'_internal/injected.dll').write_bytes(b'x')
            for check in (verify_package,standalone):
                with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_UNMANIFESTED_FILE: _internal/injected\.dll$'): check(root)


class BuildHandOverTests(unittest.TestCase):
    """The ZIP and its SHA256SUMS.txt are the whole hand-over to a company PC."""

    def test_zip_carries_the_pc_check_beside_the_installer_listed_in_the_manifest(self):
        build=runpy.run_path(str(ROOT/'scripts/build_windows_exe.py'))
        integrity=runpy.run_path(str(ROOT/'scripts/twinpulse_bootstrap_integrity.py'))
        name='twinpulse_company_pc_check.py';original=(ROOT/'scripts'/name).read_bytes()
        digest=hashlib.sha256(original).hexdigest()
        # main() runs PyInstaller and node, so it is not run here: it must stage EXTRA_FILES
        # and assemble, list and zip the package with the helpers exercised below.
        self.assertLessEqual({'EXTRA_FILES','add_top_level_files','package_files','write_zip'},
                             set(build['main'].__code__.co_names))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);resources=root/'staging/resources';package=root/'dist/TwinPulse';sources={}
            for relative in build['EXTRA_FILES']:
                build['stage'](relative,resources,sources)
            # source-manifest.json binds the shipped check to its repository bytes.
            self.assertEqual(sources['scripts/'+name],digest)
            package.mkdir(parents=True);(package/'TwinPulse.exe').write_bytes(b'owned-test-placeholder')
            build['add_top_level_files'](resources,package)
            files=build['package_files'](package)
            self.assertIn({'path':name,'bytes':len(original),'sha256':digest},files)
            (package/'windows-release-manifest.json').write_text(json.dumps({'schema':'twinpulse-windows-exe-1.0',
                'build_id':'test','source_manifest_sha256':'a'*64,'files':files}),encoding='utf-8')
            archive=root/'TwinPulse-Windows-x64-test.zip';build['write_zip'](package,archive)
            with zipfile.ZipFile(archive) as stream:stream.extractall(root/'extracted')
            extracted=root/'extracted/TwinPulse'
            # Top level of the extracted folder, next to Install-TwinPulse.cmd, byte for byte.
            self.assertTrue((extracted/'Install-TwinPulse.cmd').is_file())
            self.assertEqual((extracted/name).read_bytes(),original)
            # Install (full hash) and start (size) checks accept it: it is a listed file, not an extra one.
            self.assertEqual(verify_package(extracted)['status'],'verified')
            self.assertEqual(integrity['verify_before_import'](extracted,full=True)['build_id'],'test')
            self.assertEqual(integrity['verify_before_import'](extracted)['build_id'],'test')


if __name__ == '__main__': unittest.main()
