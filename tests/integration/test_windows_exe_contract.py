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

ROOT = Path(__file__).resolve().parents[2]
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
from twinpulse_app import CommandBroker, LocalApiServer
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.desktop_settings import read_settings, save_settings
from twinpulse_app.runtime_paths import resource_root, script_command
from twinpulse_app.windows_package import verify_package


class DesktopContractTests(unittest.TestCase):
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


if __name__ == '__main__': unittest.main()
