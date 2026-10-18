# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary synthetic presence contracts, not powered-robot acceptance."""
from datetime import datetime,timezone
from pathlib import Path
import socket
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from twinpulse_app.robot_discovery import advertised_network,discover,dns_records
from twinpulse_app.robot_registry_service import RobotRegistryService
from twinpulse_app.workspace_devices import WorkspaceDevices


def packet(ttl=120):
    def name(value):return b''.join(bytes([len(part)])+part.encode() for part in value.split('.'))+b'\0'
    def rr(owner,kind,data):return name(owner)+struct.pack('!HHIH',kind,1,ttl,len(data))+data
    instance='TurtleBot3._SSH._tcp.local';host='Burger.local'
    return struct.pack('!6H',0,0x8400,0,3,0,0)+rr('_ssh._tcp.local',12,name(instance))+rr(instance,33,struct.pack('!HHH',0,0,22)+name(host))+rr(host,1,b'\xc0\xa8\x01\x14')


def response(lifetime=30):
    return {'candidate_id':'candidate','transport':'network','address':'192.168.1.20','hostname':'burger.local',
        'label':'TurtleBot3','endpoint':{'host':'192.168.1.20','user':'twinpulse','port':22,'ros_domain_id':86},
        'identity_verified':False,'adapter_id':None,'valid_for_seconds':lifetime}


def result(candidates=None,network='completed'):
    return {'candidates':[] if candidates is None else candidates,'known_devices':[
        {'candidate_id':'cached','transport':'bluetooth','address':'00:11:22:33:44:55','label':'Remembered headset','identity_verified':False}],
        'sources':{'network':{'state':network}}}


class DiscoveryPresenceTests(unittest.TestCase):
    def service(self,root,clock,result_value):
        return RobotRegistryService(WorkspaceDevices(),root,clock=lambda:clock[0],utcnow=lambda:datetime(2026,10,16,tzinfo=timezone.utc),
            discoverer=lambda:result_value)

    def search(self,service):
        state=service.snapshot('owner')
        service.request({'action':'discover','expected_revision':state['revision']},'owner')
        service.thread.join(2)
        return service.snapshot('owner')

    def register(self,service,label='My TurtleBot',host='burger.local',port=22):
        state=service.snapshot('owner')
        return service.request({'action':'register','expected_revision':state['revision'],'label':label,'adapter_id':'unreviewed',
            'endpoint':{'host':host,'port':port,'user':'ubuntu','ros_domain_id':7}},'owner')

    def test_cached_os_inventory_never_enters_network_responses(self):
        remembered=result()['known_devices']
        with patch('twinpulse_app.robot_discovery.known_os_devices',return_value=(remembered,{})), \
             patch('twinpulse_app.robot_discovery.advertised_network',return_value=([],{'state':'completed'})):
            value=discover()
        self.assertEqual(value['candidates'],[]);self.assertEqual(value['known_devices'],remembered)

    def test_parser_preserves_display_case_and_ttl_zero_for_withdrawal(self):
        records=dns_records(packet(),include_ttl=True)
        self.assertEqual(records[1][0],'TurtleBot3._SSH._tcp.local');self.assertEqual(records[0][3],120)
        self.assertTrue(all(record[3]==0 for record in dns_records(packet(0),include_ttl=True)))

    def test_query_receipt_ttl_and_goodbye_are_bounded(self):
        def run(packets):
            clock=[0.];sent=[]
            class Source:
                def __enter__(self):return self
                def __exit__(self,*_):pass
                def settimeout(self,*_):pass
                def setsockopt(self,*_):pass
                def bind(self,*_):pass
                def sendto(self,*args):sent.append(args)
                def recvfrom(self,*_):
                    clock[0]+=.25
                    if packets:return packets.pop(0),('192.168.1.20',5353)
                    raise socket.timeout()
            value=advertised_network(socket_factory=lambda *_:Source(),clock=lambda:clock[0],timeout_s=2)
            self.assertEqual(sent[0][1],('224.0.0.251',5353));return value[0]
        live=run([packet(10)]);self.assertEqual(live[0]['label'],'TurtleBot3')
        self.assertLess(live[0]['valid_for_seconds'],10);self.assertGreater(live[0]['valid_for_seconds'],0)
        self.assertFalse(run([packet(1)]));self.assertFalse(run([packet(),packet(0)]))

    def test_saved_name_address_match_is_not_identity_or_selection(self):
        with TemporaryDirectory() as directory:
            clock=[10.];service=self.service(Path(directory),clock,result([response()]))
            before=self.register(service);before=self.register(service,'Second saved name');self.register(service,'Different port',port=2222)
            state=self.search(service);candidate=state['discovery']['candidates'][0]
            self.assertEqual([row['label'] for row in candidate['registered_matches']],['My TurtleBot','Second saved name'])
            self.assertIsNone(state['active_id']);self.assertEqual(candidate['label'],'TurtleBot3')
            self.assertTrue(all(row['connection_state']=='unverified' for row in state['robots']))
            self.assertEqual(state['robots'][0]['discovery_presence']['state'],'recent_address_response')
            self.assertFalse(state['robots'][0]['discovery_presence']['identity_verified'])
            self.assertEqual(state['robots'][2]['discovery_presence']['state'],'not_seen')
            self.assertEqual(state['robots'][0]['endpoint'],before['robots'][0]['endpoint'])

    def test_expiry_hides_responses_but_keeps_registration_and_remembered_inventory(self):
        with TemporaryDirectory() as directory:
            clock=[10.];service=self.service(Path(directory),clock,result([response()]))
            self.register(service);original=service.registry.snapshot();self.search(service);clock[0]=40.
            state=service.snapshot('owner')
            self.assertEqual(state['discovery']['freshness'],'expired');self.assertFalse(state['discovery']['candidates'])
            self.assertEqual(state['robots'][0]['discovery_presence']['state'],'unknown')
            self.assertEqual(len(state['discovery']['known_devices']),1);self.assertEqual(service.registry.snapshot(),original)

    def test_short_ttl_candidate_expiry_is_unknown_while_other_candidate_remains(self):
        with TemporaryDirectory() as directory:
            clock=[10.];other=response();other.update(candidate_id='other',address='192.168.1.21',hostname='other.local')
            service=self.service(Path(directory),clock,result([response(2),other]));self.register(service);self.search(service);clock[0]=13.
            state=service.snapshot('owner');self.assertEqual(state['discovery']['freshness'],'recent')
            self.assertEqual(state['robots'][0]['discovery_presence']['state'],'unknown')

    def test_network_unavailable_is_unknown_not_offline_or_not_seen(self):
        with TemporaryDirectory() as directory:
            clock=[10.];service=self.service(Path(directory),clock,result(network='unavailable'));self.register(service)
            state=self.search(service)
            self.assertEqual(state['robots'][0]['discovery_presence']['state'],'unknown')
            self.assertEqual(state['discovery']['freshness'],'none')

    def test_empty_recent_search_is_not_seen_not_power_off(self):
        with TemporaryDirectory() as directory:
            clock=[10.];service=self.service(Path(directory),clock,result());self.register(service)
            state=self.search(service);self.assertEqual(state['robots'][0]['discovery_presence']['state'],'not_seen')
            self.assertEqual(state['robots'][0]['connection_state'],'unverified')

    def test_legacy_cached_candidate_is_quarantined_and_metadata_get_never_searches(self):
        with TemporaryDirectory() as directory:
            clock=[10.];calls=[];value=result(result()['known_devices']);value['known_devices']=[]
            service=self.service(Path(directory),clock,value);original=service.discoverer
            service.discoverer=lambda:(calls.append(True) or original())
            self.assertFalse(service.snapshot('owner')['discovery']['candidates']);self.assertFalse(calls)
            state=self.search(service);self.assertFalse(state['discovery']['candidates']);self.assertEqual(len(state['discovery']['known_devices']),1)

    def test_old_run_result_cannot_overwrite_new_search(self):
        with TemporaryDirectory() as directory:
            clock=[10.];service=self.service(Path(directory),clock,result([response()]))
            service.discovery={'state':'running','run_id':'new','candidates':[],'known_devices':[],'sources':{}}
            service._discover('old');self.assertEqual(service.discovery['run_id'],'new');self.assertIsNone(service._discovery_finished)

    def test_receipt_deadline_does_not_restart_when_worker_returns_late(self):
        with TemporaryDirectory() as directory:
            clock=[10.];candidate=response();candidate['_expires_monotonic']=12.
            service=self.service(Path(directory),clock,result([candidate]));state=self.search(service)
            self.assertEqual(state['discovery']['candidates'][0]['remaining_seconds'],2.)
            clock[0]=12.;self.assertFalse(service.snapshot('owner')['discovery']['candidates'])

    def test_already_expired_receipt_and_withdrawn_observation_are_unknown_not_unseen(self):
        for mode in ('worker_delay','expired_during_search'):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                clock=[13.];candidate=response();candidate['_expires_monotonic']=12.
                value=result([candidate]) if mode=='worker_delay' else {**result(),'expired_candidates':[response()]}
                service=self.service(Path(directory),clock,value);self.register(service)
                state=self.search(service)
                self.assertFalse(state['discovery']['candidates']);self.assertEqual(state['discovery']['freshness'],'expired')
                self.assertEqual(state['robots'][0]['discovery_presence']['state'],'unknown')
                self.assertNotIn('_observed_candidates',state['discovery'])

    def test_expired_old_ip_record_does_not_expire_new_ip_advertisement(self):
        clock=[0.];packets=[packet(1),packet(120).replace(b'\xc0\xa8\x01\x14',b'\xc0\xa8\x01\x15')]
        class Source:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def settimeout(self,*_):pass
            def setsockopt(self,*_):pass
            def bind(self,*_):pass
            def sendto(self,*_):pass
            def recvfrom(self,*_):
                clock[0]+=.5
                if packets:return packets.pop(0),('192.168.1.20',5353)
                raise socket.timeout()
        candidates,source=advertised_network(socket_factory=lambda *_:Source(),clock=lambda:clock[0],timeout_s=2)
        self.assertEqual(candidates[0]['address'],'192.168.1.21');self.assertGreater(candidates[0]['valid_for_seconds'],0)
        self.assertTrue(source['_expired_candidates'])

    def test_failed_search_drops_old_response_and_does_not_change_saved_records(self):
        with TemporaryDirectory() as directory:
            clock=[10.];service=self.service(Path(directory),clock,result([response()]));self.register(service);self.search(service)
            def fail():raise OSError('synthetic network failure')
            service.discoverer=fail;state=self.search(service)
            self.assertEqual(state['discovery']['state'],'failed');self.assertFalse(state['discovery']['candidates'])
            self.assertEqual(state['robots'][0]['discovery_presence']['state'],'unknown')


if __name__=='__main__':unittest.main()
