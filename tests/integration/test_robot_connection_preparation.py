# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary local prerequisites contracts; no SSH, discovery or hardware."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from twinpulse_app.robot_adapters import instance_binding
from twinpulse_app.robot_connection_preparation import CHECKER_FILES, RobotConnectionPreparation
from twinpulse_app.robot_registry import RobotEndpoint
from twinpulse_app.workspace_devices import WorkspaceDevices


def binding(*, host='robot.local', port=22, ident='1'*32):
    return instance_binding({'id':ident,'adapter_id':'turtlebot3_burger_v1',
        'endpoint':{'host':host,'user':'twinpulse','port':port,'ros_domain_id':86}})


class LocalPreparationTests(unittest.TestCase):
    def test_observation_build_has_diagnostics_only_and_never_connects_on_creation_or_pc_check(self):
        with TemporaryDirectory() as directory, \
             patch.dict('os.environ',{'LOCALAPPDATA':directory}), \
             patch('twinpulse_app.device_storage.migrate_device_records',side_effect=AssertionError('No migration')), \
             patch('twinpulse_app.robot_readiness.RobotReadiness',side_effect=AssertionError('No collection')), \
             patch('twinpulse_app.physical_controller.PhysicalController',side_effect=AssertionError('No physical control')):
            root=Path(directory)
            with patch('subprocess.Popen',side_effect=AssertionError('No SSH process')):
                devices=WorkspaceDevices.from_paths(root,root/'state',physical_enabled=False,observation_enabled=True)
                try:
                    self.assertIsNotNone(devices.diagnostics);self.assertIsNotNone(devices.owner_lease)
                    self.assertIsNone(devices.readiness);self.assertIsNone(devices.controller)
                    state=devices.robot_registry_api(None,'owner')
                    self.assertTrue(state['capabilities']['read_only_connection'])
                    self.assertFalse(state['capabilities']['physical_control'])
                    self.assertEqual(state['connection']['state'],'idle')
                    self.assertIsNone(devices.diagnostics.snapshot('owner')['start_token'])
                finally:devices.close()
    def fixture(self, directory, *, runner=None, clock=lambda:10):
        root=Path(directory)
        for name in CHECKER_FILES:
            path=root/'scripts'/name;path.parent.mkdir(exist_ok=True);path.touch()
        key=root/'key';key.touch();known=root/'known';known.touch()
        calls=[]
        def lookup(command, **kwargs):
            calls.append((command,kwargs))
            return SimpleNamespace(returncode=0)
        service=RobotConnectionPreparation(root,identity=key,known_hosts=known,
            which=lambda name:'existing-'+name,runner=runner or lookup,clock=clock)
        return service,calls,key,known

    def test_local_lookup_is_bound_to_selected_host_and_nonstandard_port_without_key_reads(self):
        with TemporaryDirectory() as directory:
            service,calls,_,known=self.fixture(directory)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Do not read private keys')):
                result=service.check(binding(port=2222),7)
            self.assertTrue(result['pc_ready']);self.assertFalse(result['connection_verified'])
            self.assertEqual(result['registry_revision'],7)
            self.assertEqual(calls[0][0][1:],['-F','[robot.local]:2222','-f',str(known)])
            self.assertIs(calls[0][1]['stdout'],subprocess.DEVNULL)
            self.assertIs(calls[0][1]['stderr'],subprocess.DEVNULL)
            self.assertNotIn(str(known),str(result));self.assertFalse(result['motion_authorized'])

    def test_host_entry_missing_cannot_become_ready_from_known_hosts_existence(self):
        with TemporaryDirectory() as directory:
            service,_,_,_=self.fixture(directory,runner=lambda *a,**k:SimpleNamespace(returncode=1))
            result=service.check(binding(),1)
            self.assertFalse(result['pc_ready']);self.assertEqual(result['host_key_lookup'],'not_registered')

    def test_local_lookup_timeout_is_attention_not_connection_success(self):
        def fail(*args,**kwargs):raise subprocess.TimeoutExpired('local-lookup',3)
        with TemporaryDirectory() as directory:
            service,_,_,_=self.fixture(directory,runner=fail)
            result=service.check(binding(),1)
            self.assertFalse(result['pc_ready']);self.assertEqual(result['host_key_lookup'],'unavailable')

    def test_selection_file_change_and_age_invalidate_preparation(self):
        with TemporaryDirectory() as directory:
            now=[10];service,_,key,_=self.fixture(directory,clock=lambda:now[0])
            service.check(binding(),1)
            self.assertEqual(service.snapshot(binding(),2)['state'],'stale')
            self.assertEqual(service.snapshot(binding(ident='2'*32))['state'],'not_checked')
            key.unlink()
            self.assertEqual(service.snapshot(binding())['state'],'stale')
            key.touch();service.check(binding(),1);now[0]=131
            self.assertEqual(service.snapshot(binding())['state'],'stale')

    def test_sim_preparation_never_creates_transport_or_rewrites_registry(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);devices=WorkspaceDevices.from_paths(root,root/'state',physical_enabled=False)
            try:
                service=devices.registry_service
                service.request({'action':'register','expected_revision':0,'label':'Offline metadata',
                    'adapter_id':'turtlebot3_burger_v1','endpoint':binding()['endpoint']},'owner')
                state=service.snapshot('owner')
                state=service.request({'action':'select','expected_revision':1,'id':state['robots'][0]['id']},'owner')
                original=service.registry.path.read_bytes()
                with patch('subprocess.run',side_effect=AssertionError('No remote process')), \
                     patch.object(service.preparation,'which',return_value=None):
                    state=service.request({'action':'prepare','expected_revision':2},'owner')
                self.assertEqual(service.registry.path.read_bytes(),original)
                self.assertIsNone(devices.diagnostics);self.assertIsNone(devices.owner_lease)
                self.assertFalse(state['capabilities']['read_only_connection'])
                self.assertEqual(state['preparation']['state'],'needs_attention')
            finally:devices.close()

    def test_sim_can_list_preserved_future_adapter_metadata_without_executable_binding(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);devices=WorkspaceDevices.from_paths(root,root/'state',physical_enabled=False)
            service=devices.registry_service
            service.registry.register(label='Future hardware',adapter_id='future_adapter',
                endpoint=RobotEndpoint('future.local','ubuntu'),
                expected_revision=0,adapter_version='future-3',calibration_ref='kept-metadata')
            row=service.registry.snapshot()['robots'][0]
            service.registry.select(row['id'],expected_revision=1,assert_workspace_idle=lambda:None)
            devices.close()
            devices=WorkspaceDevices.from_paths(root,root/'state',physical_enabled=False)
            try:
                state=devices.robot_registry_api(None,'owner')
                self.assertEqual(state['robots'][0]['calibration_ref'],'kept-metadata')
                self.assertFalse(state['capabilities']['read_only_connection'])
                self.assertFalse(state['capabilities']['selected_preparation_available'])
                prepared=devices.robot_registry_api({'action':'prepare','expected_revision':2},'owner')
                self.assertEqual(prepared['preparation']['reason'],'ROBOT_ADAPTER_REVIEW_REQUIRED')
            finally:devices.close()

    def test_observation_owner_conflict_keeps_registry_and_pc_preparation(self):
        with TemporaryDirectory() as directory,patch.dict('os.environ',{'LOCALAPPDATA':directory}):
            root=Path(directory)
            first=WorkspaceDevices.from_paths(root,root/'state',physical_enabled=False,observation_enabled=True)
            try:
                second=WorkspaceDevices.from_paths(root,root/'state',physical_enabled=False,observation_enabled=True)
                try:
                    self.assertFalse(second.robot_registry_api(None,'owner')['capabilities']['read_only_connection'])
                    self.assertIsNotNone(second.registry_service)
                    self.assertEqual(second.unavailable_reason,'ROBOT_OBSERVATION_OWNER_UNAVAILABLE')
                finally:second.close()
            finally:first.close()


if __name__=='__main__':unittest.main()
