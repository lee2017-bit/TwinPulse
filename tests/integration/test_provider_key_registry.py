# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from __future__ import annotations
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.credentials import DEFAULT_CREDENTIAL_TARGET
from twinpulse_app.key_registry import KeyRegistry,KeyRegistryError
from twinpulse_app.settings import JsonProviderSettingsStore,ProviderSettings,provider_settings_preset
from twinpulse_app import CommandBroker,LocalApiServer
from twinpulse_app.command_broker import BrokerError

class Credential:
    secrets={}
    def __init__(self,target):self.target_name=target
    def load(self):return self.secrets.get(self.target_name)
    def save(self,value):self.secrets[self.target_name]=value
    def delete(self):self.secrets.pop(self.target_name,None)
    def is_configured(self):return bool(self.load())

class KeyRegistryTests(unittest.TestCase):
    def test_selection_callback_and_rollback_release_registry_before_workflow(self):
        from threading import Event,RLock,Thread
        identifier=self.register();previous=self.settings.load();seen=[]
        workflow=RLock();held=Event();callback_started=Event()
        def reader():
            with workflow:
                held.set();callback_started.wait(2)
                self.registry.settings_for_entry('legacy')
        def changed():
            callback_started.set()
            with workflow:seen.append(self.settings.load())
            reader_done=Event()
            thread=Thread(target=lambda:(self.registry.settings_for_entry('legacy'),reader_done.set()),daemon=True)
            thread.start();self.assertTrue(reader_done.wait(2));thread.join(1)
            if len(seen)==1:raise RuntimeError('deliberate reconstruction failure')
        thread=Thread(target=reader,daemon=True);thread.start();self.assertTrue(held.wait(1))
        with self.assertRaisesRegex(KeyRegistryError,'이전 설정'):
            self.registry.select(identifier,changed)
        thread.join(2);self.assertFalse(thread.is_alive());self.assertEqual(len(seen),2)
        self.assertEqual(self.settings.load(),previous)

    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        Credential.secrets={DEFAULT_CREDENTIAL_TARGET:'old-nebius-secret'}
        self.settings=JsonProviderSettingsStore(Path(self.temp.name)/'settings.json')
        self.settings.save(provider_settings_preset('nebius_token_factory'))
        self.legacy=Credential(DEFAULT_CREDENTIAL_TARGET)
        self.registry=KeyRegistry(self.settings,self.legacy,Credential)

    def register(self,**overrides):
        body={'name':'GPT','provider_profile':'openai','model_id':'gpt-5.4-mini','api_key':'new-secret-canary'}
        body.update(overrides)
        result=self.registry.register(body)
        return result['entries'][-1]['id']

    def test_register_select_restart_preserves_existing_and_has_no_secret_export(self):
        identifier=self.register()
        self.assertEqual(self.settings.load().provider_profile,'nebius_token_factory')
        result=self.registry.select(identifier,lambda:None)
        self.assertTrue(result['entries'][-1]['active'])
        self.assertEqual(self.registry.resolve(self.settings.load()).load(),'new-secret-canary')
        self.assertEqual(self.legacy.load(),'old-nebius-secret')
        restarted=KeyRegistry(self.settings,self.legacy,Credential)
        restarted.select('legacy',lambda:None)
        self.assertEqual(self.settings.load().provider_profile,'nebius_token_factory')
        for text in (json.dumps(result),self.registry.path.read_text(encoding='utf-8'),self.settings.path.read_text(encoding='utf-8')):
            self.assertNotIn('new-secret-canary',text)
            self.assertNotIn('old-nebius-secret',text)

    def test_multiple_keys_can_be_selected_independently(self):
        first=self.register()
        second=self.register(name='GPT2',api_key='second')
        self.registry.select(second,lambda:None)
        self.assertEqual(self.registry.resolve(self.settings.load()).load(),'second')
        self.registry.select(first,lambda:None)
        self.assertEqual(self.registry.resolve(self.settings.load()).load(),'new-secret-canary')

    def test_stage_lookup_does_not_switch_active_key(self):
        identifier=self.register()
        self.registry.select(identifier,lambda:None)
        before=self.settings.load()
        self.assertEqual(self.registry.settings_for_entry('legacy').provider_profile,'nebius_token_factory')
        self.assertEqual(self.registry.settings_for_entry(identifier),before)
        self.assertEqual(self.settings.load(),before)
        with self.assertRaises(KeyRegistryError):self.registry.settings_for_entry('missing')

    def test_other_origin_or_provider_cannot_receive_same_key(self):
        identifier=self.register()
        self.registry.select(identifier,lambda:None)
        from dataclasses import replace
        active=self.settings.load()
        for value in (replace(active,base_url='https://evil.example/v1/'),
                      provider_settings_preset('nebius_token_factory',credential_ref=active.credential_ref)):
            with self.assertRaises(KeyRegistryError) as error:self.registry.resolve(value)
            self.assertEqual(error.exception.code,'credential_binding_mismatch')

    def test_registration_failure_rolls_back_new_key_only(self):
        original=self.registry._save
        self.registry._save=lambda entries: (_ for _ in ()).throw(OSError('secret-canary'))
        with self.assertRaises(KeyRegistryError) as error:self.register()
        self.assertEqual(error.exception.code,'key_registry_save_failed')
        self.assertNotIn('secret-canary',str(error.exception))
        self.assertEqual(Credential.secrets,{DEFAULT_CREDENTIAL_TARGET:'old-nebius-secret'})
        self.registry._save=original

    def test_failed_composition_rolls_back_selection(self):
        identifier=self.register()
        previous=self.settings.load()
        calls=[]
        def changed():
            calls.append(self.settings.load().provider_profile)
            if calls[-1]=='openai':raise ValueError('unsupported adapter')
        with self.assertRaises(KeyRegistryError) as error:self.registry.select(identifier,changed)
        self.assertEqual(error.exception.code,'provider_switch_failed')
        self.assertEqual(calls,['openai','nebius_token_factory'])
        self.assertEqual(self.settings.load(),previous)

    def test_delete_requires_inactive_nonlegacy_and_missing_key_is_visible(self):
        identifier=self.register()
        self.registry.select(identifier,lambda:None)
        for target in (identifier,'legacy'):
            with self.assertRaises(KeyRegistryError):self.registry.remove(target)
        self.registry.select('legacy',lambda:None)
        Credential(self.registry.entry(identifier)['settings']['credential_ref']).delete()
        self.assertFalse(self.registry.state()['entries'][-1]['configured'])
        with self.assertRaises(KeyRegistryError):self.registry.select(identifier,lambda:None)
        self.registry.remove(identifier)
        self.assertEqual(len(self.registry.state()['entries']),1)

    def test_invalid_body_and_tampered_ref_preserve_files(self):
        for overrides in ({'api_key':''},{'api_key':'bad\nvalue'},{'provider_profile':'OPENAI'},
                          {'model_id':''},{'name':'\n'},{'api_key':'a'*1281}):
            with self.assertRaises(KeyRegistryError):self.register(**overrides)
        identifier=self.register()
        data=json.loads(self.registry.path.read_text(encoding='utf-8'))
        data['entries'][-1]['settings']['credential_ref']='OtherApp/Secret'
        self.registry.path.write_text(json.dumps(data),encoding='utf-8')  # test-only adversarial metadata
        with self.assertRaises(KeyRegistryError) as error:self.registry.entry(identifier)
        self.assertEqual(error.exception.code,'key_registry_corrupt')
        self.assertTrue(self.registry.path.exists())

    def test_api_uses_selected_store_and_rejects_legacy_cross_provider_rebind(self):
        server=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*40,engine_bootstrap_secret='e'*40,
            provider_settings_store=self.settings,credential_store=self.legacy,key_registry=self.registry)
        self.addCleanup(server._httpd.server_close)
        result=server._provider_keys({'action':'register','name':'GPT','provider_profile':'openai',
            'model_id':'gpt-5.4-mini','api_key':'new-secret-canary'})
        identifier=result['entries'][-1]['id']
        server._provider_keys({'action':'select','id':identifier})
        self.assertTrue(server._provider_settings()['credential_configured'])
        with self.assertRaises(BrokerError):server._save_provider_settings({'provider_profile':'nebius_token_factory',
            'base_url':'https://api.tokenfactory.nebius.com/v1/','model_id':'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
            'reasoning_effort':'low','credential_reapproval':True,'api_key':'override'})
        self.assertEqual(self.legacy.load(),'old-nebius-secret')

    def test_http_auth_csrf_roundtrip_no_secret_export(self):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        server=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*40,engine_bootstrap_secret='e'*40,
            provider_settings_store=self.settings,credential_store=self.legacy,key_registry=self.registry)
        server.start()
        self.addCleanup(server.stop)
        def request(path,body=None,headers=None):
            selected=dict(headers or {})
            if body is not None:selected['Content-Type']='application/json'
            req=Request(server.base_url+path,data=json.dumps(body).encode() if body is not None else None,headers=selected)
            try:
                with urlopen(req,timeout=3) as response:return response.status,json.loads(response.read()),response.headers
            except HTTPError as error:return error.code,json.loads(error.read()),error.headers
        path='/v1/product/provider-keys'
        self.assertEqual(request(path)[0],401)
        _,session,headers=request('/v1/bootstrap',{'role':'product','secret':'p'*40})
        cookie={'Cookie':headers['Set-Cookie'].split(';')[0]}
        self.assertEqual(request(path,{'action':'register'},cookie)[0],403)
        auth={**cookie,'X-TwinPulse-CSRF':session['csrf_token']}
        status,result,_=request(path,{'action':'register','name':'GPT','provider_profile':'openai',
            'model_id':'gpt-5.4-mini','api_key':'new-secret-canary'},auth)
        self.assertEqual(status,200)
        self.assertNotIn('new-secret-canary',json.dumps(result))
        identifier=result['entries'][-1]['id']
        self.assertEqual(request(path,{'action':'select','id':identifier},auth)[0],200)
        self.assertEqual(request('/v1/product/provider-settings',headers=cookie)[1]['model_id'],'gpt-5.4-mini')
        self.assertEqual(request(path,{'action':'remove','id':identifier},auth)[1]['error']['code'],'key_delete_locked')

    def test_gateway_refresh_is_blocked_during_generation(self):
        server=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*40,engine_bootstrap_secret='e'*40,
            provider_settings_store=self.settings,credential_store=self.legacy,key_registry=self.registry)
        self.addCleanup(server._httpd.server_close)
        from types import SimpleNamespace
        server.product_workflow=SimpleNamespace(snapshot=lambda:{'phase':'generating'})
        identifier=self.register()
        with self.assertRaises(BrokerError) as error:server._provider_keys({'action':'select','id':identifier})
        self.assertEqual(error.exception.code,'generation_busy')
        self.assertEqual(self.settings.load().provider_profile,'nebius_token_factory')

    def test_openai_composition_is_zero_call_and_cannot_borrow_nebius_budget(self):
        from twinpulse_app.provider_composition import build_live_generation_service
        from twinpulse_provider import ProviderConfigurationError
        key_reads=[]
        def getter():key_reads.append(True);return 'test-only'
        value=ProviderSettings(model_id='gpt-5.4-mini')
        build_live_generation_service(value,getter,evidence_root=Path(self.temp.name)/'evidence')
        self.assertEqual(key_reads,[])
        with self.assertRaises(ProviderConfigurationError):
            build_live_generation_service(value,getter,campaign=object())
        self.assertEqual(key_reads,[])

if __name__=='__main__':unittest.main()
