# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary offline registry/discovery/command-pin contracts; no devices."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import socket
import struct
import subprocess
from tempfile import TemporaryDirectory
from threading import Event,Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.integration import test_r5_product_api
from tests.integration.test_robot_diagnostics import fixture,observation
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.robot_adapters import ADAPTERS,instance_binding,legacy_binding
from twinpulse_app.robot_registry import RobotEndpoint
from twinpulse_app.robot_registry_service import RobotRegistryService
from twinpulse_app.robot_discovery import advertised_candidates,advertised_network,dns_records
from twinpulse_app.workspace_devices import WorkspaceDevices
from twinpulse_app.robot_readiness import RobotReadiness
from twinpulse_app.physical_controller import PhysicalController,worker_command
from twinpulse_app.robot_evidence_export import export_finished_session
from twinpulse_app.robot_evidence_recovery import RobotEvidenceRecovery


def binding(host='burger-new.local', *, user='twinpulse',port=22,domain=86,ident='1'*32):
    return instance_binding({'id':ident,'adapter_id':ADAPTERS[0]['id'],
        'endpoint':asdict(RobotEndpoint(host,user,port,domain))})


def register_selected_robot(service):
    """Explicit test setup: a fresh user has no developer robot to import."""
    state=service.snapshot('owner')
    state=service.request({'action':'register','label':'Existing test robot','adapter_id':ADAPTERS[0]['id'],
        'endpoint':binding('previous-robot.local')['endpoint'],'expected_revision':state['revision']},'owner')
    return service.request({'action':'select','id':state['robots'][0]['id'],
        'expected_revision':state['revision']},'owner')


class RegistryBindingTests(unittest.TestCase):
    def test_connect_pins_revision_and_selected_endpoint_after_another_service_changes_selection(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);diagnostics=fixture(root,lambda *a,**k:self.fail('No remote call'))
            service=RobotRegistryService(WorkspaceDevices(diagnostics=diagnostics),root/'registry')
            register_selected_robot(service)
            state=service.snapshot('owner')
            service.request({'action':'register','label':'Second robot','adapter_id':ADAPTERS[0]['id'],
                'endpoint':binding('second.local')['endpoint'],'expected_revision':state['revision']},'owner')
            other=RobotRegistryService(WorkspaceDevices(),root/'registry')
            state=other.snapshot('other');second=state['robots'][1]['id']
            state=other.request({'action':'select','id':second,'expected_revision':state['revision']},'other')
            targets=[]
            with patch.object(diagnostics,'preflight',return_value={'start_token':'fixture-token'}), \
                 patch.object(diagnostics,'start',side_effect=lambda *a:targets.append(diagnostics._instance['endpoint']['host'])):
                service.request({'action':'connect','expected_revision':state['revision']},'owner')
            self.assertEqual(targets,['second.local'])
            original=service.registry.active_at_revision
            def change_before_pin(expected):
                other.registry.select(state['robots'][0]['id'],expected_revision=state['revision'],assert_workspace_idle=lambda:None)
                return original(expected)
            with patch.object(service.registry,'active_at_revision',side_effect=change_before_pin), \
                 patch.object(diagnostics,'start',side_effect=AssertionError('Stale selection must not execute')):
                with self.assertRaises(BrokerError) as conflict:
                    service.request({'action':'connect','expected_revision':state['revision']},'owner')
                self.assertEqual(conflict.exception.code,'robot_registry_changed')
            diagnostics.close()

    def test_sim_package_exposes_registry_without_physical_services_or_migration(self):
        with TemporaryDirectory() as directory, \
                patch('twinpulse_app.device_storage.DeviceOwnerLease',side_effect=AssertionError('No physical lease')), \
                patch('twinpulse_app.device_storage.migrate_device_records',side_effect=AssertionError('No migration')):
            root=Path(directory)
            devices=WorkspaceDevices.from_paths(root/'source',root/'state',physical_enabled=False)
            try:
                self.assertIsNone(devices.controller)
                self.assertIsNone(devices.diagnostics)
                self.assertIsNone(devices.readiness)
                self.assertIsNone(devices.owner_lease)
                self.assertEqual(devices.robot_registry_api(None,'owner')['robots'],[])
                state=register_selected_robot(devices.registry_service)
                with self.assertRaisesRegex(BrokerError,'Read-only diagnostics is unavailable'):
                    devices.robot_registry_api({'action':'connect','expected_revision':state['revision']},'owner')
                self.assertFalse(devices.snapshot()['motion_authorized'])
            finally:devices.close()
    def test_verified_label_requires_same_instance_authenticated_fresh_observation(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);diagnostics=fixture(root,lambda *a,**k:self.fail('No actual observation'))
            devices=WorkspaceDevices(diagnostics=diagnostics);service=RobotRegistryService(devices,root/'registry')
            register_selected_robot(service)
            diagnostics._reports.import_report(observation())
            diagnostics._job={'id':'fixture','status':'COMPLETED','result_code':'OBSERVATION_RECEIVED',
                              'robot_binding':instance_binding(service.registry.active()),'authentication_verified':False}
            self.assertEqual(service.snapshot('owner')['robots'][0]['connection_state'],'unverified')
            diagnostics._job['authentication_verified']=True
            self.assertEqual(service.snapshot('owner')['robots'][0]['connection_state'],'verified_observation')
            diagnostics._job['robot_binding']=binding('other.local')
            self.assertEqual(service.snapshot('owner')['robots'][0]['connection_state'],'unverified')
            diagnostics.close()

    def test_metadata_get_register_select_never_discovers_or_opens_transport_and_clears_old_diagnostics(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);calls=[]
            diagnostics=fixture(root,lambda *a,**k:calls.append((a,k)))
            devices=WorkspaceDevices(diagnostics=diagnostics)
            discover_calls=[]
            service=RobotRegistryService(devices,root/'registry',discoverer=lambda:discover_calls.append(True))
            devices.registry_service=service
            register_selected_robot(service)
            initial=devices.robot_registry_api(None,'owner')
            self.assertEqual(len(initial['robots']),1)
            self.assertEqual(initial['robots'][0]['connection_state'],'unverified')
            diagnostics.preflight('owner')
            diagnostics._reports.import_report(observation())
            value=devices.robot_registry_api({'action':'register','expected_revision':initial['revision'],
                'label':'Second robot','adapter_id':ADAPTERS[0]['id'],'endpoint':binding()['endpoint']},'owner')
            original=initial['active_id'];added=next(row for row in value['robots'] if row['id']!=original)
            value=devices.robot_registry_api({'action':'select','id':added['id'],'expected_revision':value['revision']},'owner')
            current=diagnostics.snapshot('owner')
            self.assertIsNone(current['record']);self.assertIsNone(current['start_token']);self.assertEqual(current['target'],'twinpulse@burger-new.local')
            self.assertEqual(value['active_id'],added['id']);self.assertFalse(calls);self.assertFalse(discover_calls)
            with self.assertRaises(BrokerError):devices.robot_registry_api({'action':'select','id':original,'expected_revision':initial['revision']},'owner')
            devices.close()

    def test_two_concurrent_selects_use_one_workspace_lock_and_one_revision(self):
        with TemporaryDirectory() as directory:
            devices=WorkspaceDevices();service=RobotRegistryService(devices,directory);devices.registry_service=service
            register_selected_robot(service)
            state=service.snapshot('owner');old=state['active_id']
            service.request({'action':'register','label':'New','adapter_id':'unreviewed','endpoint':binding()['endpoint'],'expected_revision':state['revision']},'owner')
            state=service.snapshot('owner');new=next(row['id'] for row in state['robots'] if row['id']!=old)
            outcomes=[]
            def select(target):
                try:outcomes.append(service.request({'action':'select','id':target,'expected_revision':state['revision']},'owner')['active_id'])
                except BrokerError:outcomes.append('rejected')
            threads=[Thread(target=select,args=(target,)) for target in (old,new)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
            self.assertEqual(outcomes.count('rejected'),1)
            self.assertEqual(service.snapshot('owner')['revision'],state['revision']+1)

    def test_discovery_is_explicit_async_and_does_not_register_candidates(self):
        with TemporaryDirectory() as directory:
            release=Event();entered=Event()
            def discoverer():entered.set();release.wait(2);return {'candidates':[],'sources':{'network':{'state':'completed'}}}
            devices=WorkspaceDevices();service=RobotRegistryService(devices,directory,discoverer=discoverer)
            state=service.snapshot('owner');count=len(state['robots'])
            with patch('socket.socket',side_effect=AssertionError('No direct network permitted')):
                state=service.request({'action':'discover','expected_revision':state['revision']},'owner')
                self.assertTrue(entered.wait(1));self.assertEqual(state['discovery']['state'],'running')
                with self.assertRaises(BrokerError):service.request({'action':'select','id':None,'expected_revision':state['revision']},'owner')
                release.set();service.thread.join(2)
                state=service.snapshot('owner');self.assertEqual(state['discovery']['state'],'completed');self.assertEqual(len(state['robots']),count)

    def test_observation_propagates_selected_user_port_and_domain_then_switch_cannot_reuse_token(self):
        with TemporaryDirectory() as directory:
            calls=[];service=fixture(Path(directory),lambda *a,**k:(calls.append((a,k)) or observation()))
            original=service.preflight('owner')['start_token']
            service.bind_instance(binding(user='ubuntu',port=2222,domain=7))
            with self.assertRaises(BrokerError):service.start('owner',original,True)
            token=service.preflight('owner')['start_token'];service.start('owner',token,True);service._thread.join(3)
            self.assertEqual(calls[0][0],('burger-new.local','ubuntu'))
            self.assertEqual(calls[0][1]['port'],2222);self.assertEqual(calls[0][1]['domain_id'],7)
            self.assertEqual(service.snapshot('owner')['job']['robot_binding'],binding(user='ubuntu',port=2222,domain=7))
            self.assertFalse(service.snapshot('owner')['job']['authentication_verified'])
            service.close()

    def test_unknown_adapter_stays_metadata_only_and_active_operation_blocks_selection(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);diagnostics=fixture(root,lambda *a,**k:self.fail('No connection allowed'))
            devices=WorkspaceDevices(diagnostics=diagnostics);service=RobotRegistryService(devices,root/'registry')
            state=service.snapshot('owner');state=service.request({'action':'register','label':'Unknown','adapter_id':'unreviewed','endpoint':binding()['endpoint'],'expected_revision':state['revision']},'owner')
            target=next(row['id'] for row in state['robots'] if row['adapter_id']=='unreviewed')
            diagnostics._job={'status':'RUNNING'}
            with self.assertRaises(BrokerError):service.request({'action':'select','id':target,'expected_revision':state['revision']},'owner')
            diagnostics._job=None
            state=service.request({'action':'select','id':target,'expected_revision':state['revision']},'owner')
            with self.assertRaises(BrokerError):service.request({'action':'connect','expected_revision':state['revision']},'owner')
            diagnostics.close()


class EndpointCommandTests(unittest.TestCase):
    def test_selection_does_not_carry_ready_voltage_or_remove_uncertain_global_gate(self):
        with TemporaryDirectory() as directory:
            controller=PhysicalController(directory,command=lambda *_:['fixture'])
            controller.state={'state':'FINISHED','voltage_v':12.0,'physical_verified':True,'cleanup_confirmed':True}
            controller.challenge='old';controller.last_trial={'status':'QUALIFIED'}
            controller.bind_instance(binding())
            self.assertNotIn('voltage_v',controller.snapshot(None));self.assertFalse(controller.snapshot(None)['physical_verified'])
            self.assertIsNone(controller.challenge);self.assertIsNone(controller.last_trial)
            readiness=RobotReadiness(directory);readiness._state.update(status='COLLECTED_UNALIGNED',job_id='a'*32,result={'status':'old'})
            readiness.bind_instance(binding())
            self.assertEqual(readiness.snapshot(None)['status'],'NOT_STARTED')
            self.assertEqual(readiness.snapshot(None)['historical_robot_record']['job_id'],'a'*32)
            readiness._state['status']='REMOTE_STATE_UNKNOWN'
            self.assertTrue(readiness.blocks_robot_operation());self.assertEqual(readiness.snapshot(None)['status'],'REMOTE_STATE_UNKNOWN')
            controller.close();readiness.close()

    def test_worker_function_identity_and_endpoint_commands_are_preserved_without_launch(self):
        with TemporaryDirectory() as directory,patch('pathlib.Path.is_file',return_value=True),patch('shutil.which',return_value='fixture-ssh'):
            controller=PhysicalController(directory)
            self.assertIs(controller.command,worker_command);self.assertTrue(controller.real_transport)
            command=worker_command(directory,'control',robot_binding=binding())
            self.assertIn('twinpulse@burger-new.local',command);self.assertNotIn('twinpulse@192.168.35.139',command)
            prepare=worker_command(Path(directory),'prepare',robot_binding=binding())
            self.assertEqual(prepare[prepare.index('--host')+1],'burger-new.local')
            for value in (binding(user='ubuntu'),binding(port=2222),binding(domain=7)):
                with self.assertRaises(BrokerError):worker_command(directory,'prepare',robot_binding=value)
            controller.close()

    def test_readiness_start_and_resume_commands_use_original_job_not_new_selection(self):
        with TemporaryDirectory() as directory:
            service=RobotReadiness(directory);service._job_binding=binding('original.local')
            service.bind_instance(binding('other.local',ident='2'*32));commands=[]
            def run(command,**_):commands.append(command);return subprocess.CompletedProcess(command,2,b'',b'')
            with patch('twinpulse_app.robot_readiness.subprocess.run',side_effect=run):
                with self.assertRaises(ValueError):service._run_cli()
                with self.assertRaises(OSError):service._run_resume_cli(Path(directory)/'artifacts/robot-preparation/20261016T000000Z-aaaaaaaa/result/report.json')
            self.assertEqual(len(commands),2)
            for command in commands:self.assertEqual(command[command.index('--host')+1],'original.local')
            self.assertFalse(service.snapshot(None)['selected_instance_matches_job'])
            service.close()

    def test_transfer_uses_immutable_original_host_and_recovery_passes_its_sidecar(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);job='a'*32;target=root/'artifacts/manual-control'/job;target.mkdir(parents=True)
            report={'robot_session_id':'manual-'+'b'*32,'mode':'off','boot_id':'boot','release_id':'release'}
            original=binding('original.local');(target/'robot-report.json').write_text(json.dumps(report));(target/'robot-binding.json').write_text(json.dumps(original))
            key=root/'dummy-key';known=root/'dummy-known';key.touch();known.touch();commands=[]
            def run(command,**_):commands.append(command);return subprocess.CompletedProcess(command,1,b'',b'')
            receipt=export_finished_session(report,root/'exports',robot_binding=original,runner=run,scp='fixture-scp',key=key,known=known)
            self.assertEqual(receipt['status'],'INCOMPLETE');self.assertTrue(commands)
            self.assertTrue(all('twinpulse@original.local:' in command[-2] for command in commands))
            calls=[]
            def exporter(report,destination,**kwargs):calls.append(kwargs);return {'status':'INCOMPLETE'}
            with patch('twinpulse_app.robot_evidence_recovery.export_finished_session',exporter):
                recovery=RobotEvidenceRecovery(root,exporter=exporter);recovery.start('owner',job,'c'*32);recovery.thread.join(2)
            self.assertEqual(calls,[{'robot_binding':original}])


class AdvertisedDiscoveryTests(unittest.TestCase):
    def test_parser_accepts_only_advertised_service_and_never_claims_identity(self):
        def name(value):return b''.join(bytes([len(part)])+part.encode() for part in value.split('.'))+b'\0'
        def record(owner,kind,data):return name(owner)+struct.pack('!HHIH',kind,1,120,len(data))+data
        instance='Burger._ssh._tcp.local';host='burger.local'
        raw=struct.pack('!6H',0,0x8400,0,3,0,0)+record('_ssh._tcp.local',12,name(instance))+record(instance,33,struct.pack('!HHH',0,0,2222)+name(host))+record(host,1,b'\xc0\xa8\x01\x14')
        candidates=advertised_candidates(dns_records(raw));self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['endpoint']['host'],'192.168.1.20');self.assertEqual(candidates[0]['endpoint']['port'],2222)
        self.assertIsNone(candidates[0]['adapter_id']);self.assertFalse(candidates[0]['identity_verified'])
        self.assertFalse(advertised_candidates([('unadvertised._ssh._tcp.local','SRV',(host,22))]))
        with self.assertRaises(ValueError):dns_records(struct.pack('!6H',0,0x8400,0,1,0,0)+b'\xc0\x0c')

    def test_network_query_only_targets_mdns_multicast_and_is_bounded(self):
        sent=[];ticks=iter([0,.1,1,2,3,4,5])
        class FakeSocket:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def settimeout(self,*_):pass
            def setsockopt(self,*_):pass
            def bind(self,*_):pass
            def sendto(self,*args):sent.append(args)
            def recvfrom(self,*_):raise socket.timeout()
        candidates,source=advertised_network(socket_factory=lambda *_:FakeSocket(),clock=lambda:next(ticks),timeout_s=2)
        self.assertEqual(candidates,[]);self.assertEqual(source['scope'],'advertised_mdns_only')
        self.assertEqual(len(sent),1);self.assertEqual(sent[0][1],('224.0.0.251',5353))


if __name__=='__main__':unittest.main()
