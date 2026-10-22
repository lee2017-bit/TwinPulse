# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Document/device separation and OS ownership; no robot transport is invoked."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import hashlib
import json
import unittest

from twinpulse_app.api import LocalApiServer
from twinpulse_app.command_broker import BrokerError, CommandBroker
from twinpulse_app.device_storage import DeviceOwnerLease, migrate_device_records, diagnostic_retention
from twinpulse_app.robot_readiness import RobotReadiness
from twinpulse_app.workspace_devices import WorkspaceDevices
from tests.integration.test_robot_readiness_app import precollection_fixture


class WorkspaceDevicesTests(unittest.TestCase):
    def test_shared_bind_operation_cancels_review_without_waiting(self):
        from unittest.mock import Mock
        devices=WorkspaceDevices();review=Mock();devices.physical_fleet=SimpleNamespace(motion_reviews=review)
        devices.bind_operation(SimpleNamespace(product_workflow=None))
        review.cancel_for_start.assert_called_once_with('PHYSICAL_START');review.close.assert_not_called()

    def test_cleanup_attempts_every_owner_after_an_earlier_failure(self):
        from unittest.mock import Mock
        devices=WorkspaceDevices();services=[Mock() for _ in range(6)];original=OSError('original owner failure')
        services[0].close.side_effect=original
        for name,service in zip(('physical_fleet','controller','diagnostics','readiness','registry_service','owner_lease'),services):setattr(devices,name,service)
        with self.assertRaises(ExceptionGroup) as raised:devices.close()
        self.assertIs(raised.exception.exceptions[0],original)
        for service in services:service.close.assert_called_once_with()

    def test_past_failed_missing_and_corrupt_records_do_not_lock_documents(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = precollection_fixture(root)
            original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            for content in ('original', 'corrupt', 'absent'):
                if content == 'corrupt':
                    paths[0].write_text('invalid json')
                elif content == 'absent':
                    paths[0].unlink()
                readiness = RobotReadiness(root, runner=lambda: self.fail('No robot call'))
                devices = WorkspaceDevices(readiness=readiness)
                api = LocalApiServer(CommandBroker(), product_bootstrap_secret='p'*32,
                                     engine_bootstrap_secret='e'*32, workspace_devices=devices)
                try:
                    with api._scene_edit_admission('project-switch'):
                        pass
                    if content == 'original':
                        self.assertTrue(readiness.blocks_robot_operation())
                        self.assertEqual(original, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
                finally:
                    api.stop()
                    api._httpd.server_close()

    def test_all_contexts_share_one_device_owner_and_start_lock(self):
        with TemporaryDirectory() as directory:
            readiness = RobotReadiness(directory, runner=lambda: self.fail('No robot call'))
            devices = WorkspaceDevices(readiness=readiness)
            first = LocalApiServer(CommandBroker(), product_bootstrap_secret='p'*32,
                                  engine_bootstrap_secret='e'*32, workspace_devices=devices)
            second = LocalApiServer(CommandBroker(project_id='another_chat'), virtual=True,
                                   product_bootstrap_secret='p'*32, engine_bootstrap_secret='e'*32,
                                   workspace_devices=devices)
            try:
                self.assertIs(first._robot_start_lock, second._robot_start_lock)
                self.assertIs(first.robot_readiness, second.robot_readiness)
                second.stop()
                self.assertFalse(devices.closed)
                first.chat_robot_preparation.thread = SimpleNamespace(is_alive=lambda: True)
                with self.assertRaises(BrokerError):
                    with second._scene_edit_admission('project-switch'):
                        pass
                first.chat_robot_preparation.thread = None
                readiness._resume_thread = SimpleNamespace(is_alive=lambda: True)
                with self.assertRaises(BrokerError):
                    with second._scene_edit_admission('project-switch'):
                        pass
                readiness._resume_thread = None
            finally:
                first.stop()
                first._httpd.server_close()
            self.assertTrue(devices.closed)

    def test_cross_process_owner_is_os_lock_not_historical_file_content(self):
        import os
        import subprocess
        import sys
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'owner.lock'
            script=('import sys; from twinpulse_app.device_storage import DeviceOwnerLease; '
                    '\ntry: lease=DeviceOwnerLease(sys.argv[1])\nexcept OSError: sys.exit(3)\nelse: lease.close()')
            environment={**os.environ,'PYTHONPATH':os.pathsep.join(str(Path(entry or '.').resolve()) for entry in sys.path)}
            first = DeviceOwnerLease(path)
            try:
                with self.assertRaises(OSError):
                    DeviceOwnerLease(path)
                child=subprocess.run([sys.executable,'-B','-c',script,str(path)],env=environment,capture_output=True,timeout=10)
                self.assertEqual(child.returncode,3,child.stderr.decode())
            finally:
                first.close()
            child=subprocess.run([sys.executable,'-B','-c',script,str(path)],env=environment,capture_output=True,timeout=10)
            self.assertEqual(child.returncode,0,child.stderr.decode())
            second = DeviceOwnerLease(path)
            second.close()
            self.assertTrue(path.is_file())

    def test_migration_preserves_original_bytes_and_is_repeatable(self):
        with TemporaryDirectory() as directory:
            source, data = Path(directory)/'installed', Path(directory)/'user'
            paths = precollection_fixture(source)
            original = paths[0].read_bytes()
            migrate_device_records(source, data)
            saved = data/'artifacts/robot-readiness-app/current.json'
            self.assertEqual(saved.read_bytes(), original)
            self.assertEqual(paths[0].read_bytes(), original)
            state = RobotReadiness(source, archive_root=data)
            self.assertTrue(state.blocks_robot_operation())
            self.assertFalse(state.local_operation_active())
            saved.write_text(json.dumps({'new': 'current user state'}))
            migrate_device_records(source, data)
            self.assertEqual(json.loads(saved.read_text()), {'new': 'current user state'})
            self.assertEqual(paths[0].read_bytes(), original)

    def test_retention_archives_only_finished_diagnostics_and_keeps_active_and_projects(self):
        import os
        with TemporaryDirectory() as directory:
            root=Path(directory)
            old=root/'artifacts/robot-console'/('a'*32)
            active=root/'artifacts/robot-console'/('b'*32)
            for folder in (old,active):
                folder.mkdir(parents=True)
                (folder/'report.json').write_text('{"status":"historical"}')
                os.utime(folder,(1,1))
            source=(old/'report.json').read_bytes()
            project=root/'projects/room/project.json';project.parent.mkdir(parents=True);project.write_text('{}')
            current=root/'artifacts/robot-readiness-app/current.json';current.parent.mkdir(parents=True);current.write_text('{"status":"REMOTE_STATE_UNKNOWN"}')
            preview=diagnostic_retention(root,active_job='b'*32)
            self.assertEqual(preview['eligible_count'],1);self.assertTrue(old.is_dir())
            result=diagnostic_retention(root,archive=True,active_job='b'*32)
            self.assertEqual(result['archived_count'],1);self.assertFalse(old.exists());self.assertTrue(active.is_dir())
            copied=list((root/'retired-diagnostics').glob('*/'+'a'*32+'/report.json'))
            self.assertEqual(copied[0].read_bytes(),source)
            self.assertEqual(project.read_text(),'{}')
            self.assertEqual(current.read_text(),'{"status":"REMOTE_STATE_UNKNOWN"}')


if __name__ == '__main__':
    unittest.main()
