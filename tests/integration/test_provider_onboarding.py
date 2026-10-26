# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Metadata fixtures only; real metadata setup is a separate verification."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tests.integration.test_provider_key_registry import Credential
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.settings import JsonProviderSettingsStore,provider_settings_preset
from twinpulse_app.credentials import DEFAULT_CREDENTIAL_TARGET
from twinpulse_app.provider_onboarding import configure_first_nebius_key,refresh_model_catalog
from twinpulse_app.stage_routing import StageRoutingSettings

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);Credential.secrets={}
        self.registry=KeyRegistry(JsonProviderSettingsStore(Path(self.temp.name)/'settings.json'),Credential(DEFAULT_CREDENTIAL_TARGET),Credential)
        result=self.registry.register(dict(name='Nebius',provider_profile='nebius_token_factory',
            model_id=provider_settings_preset('nebius_token_factory').model_id,api_key='local-test-canary'))
        self.key=result['entries'][-1]['id'];self.calls=[]
    def get(self,url,credential):
        self.calls.append(url)
        models=['deepseek-ai/DeepSeek-V4.1-Flash','nvidia/nemotron-3-super-120b-a12b']
        if url.endswith('models_info'):
            return [dict(flavors=[dict(model_id=m,use_cases=['text','image'] if i==0 else ['text'],
                max_model_len=262144,input_price_per_million_tokens=.3,output_price_per_million_tokens=.9)
                for i,m in enumerate(models)])],'a'*64
        return dict(data=[dict(id=m) for m in models]),'b'*64
    def test_first_key_applies_exact_models_from_current_metadata_without_inference(self):
        changed=[];result=configure_first_nebius_key(self.registry,self.key,lambda:changed.append(True),get=self.get)
        route=StageRoutingSettings(self.registry).load()
        self.assertEqual(route['observer']['model_id'],'deepseek-ai/DeepSeek-V4.1-Flash')
        self.assertEqual(route['planner']['model_id'],'nvidia/nemotron-3-super-120b-a12b')
        self.assertEqual(result['state'],'applied');self.assertEqual(len(self.calls),2);self.assertEqual(changed,[True])
        self.assertNotIn('local-test-canary',StageRoutingSettings(self.registry).path.read_text())
    def test_existing_choice_is_never_automatically_replaced(self):
        configure_first_nebius_key(self.registry,self.key,lambda:None,get=self.get)
        self.calls=[]
        with self.assertRaisesRegex(Exception,'기존 모델 설정'):
            configure_first_nebius_key(self.registry,self.key,lambda:None,get=self.get)
        self.assertEqual(self.calls,[])
    def test_unavailable_model_preserves_key_and_does_not_save_route(self):
        def unavailable(url,credential):
            result,sha=self.get(url,credential)
            if url.endswith('/models'):result={'data':[]}
            return result,sha
        with self.assertRaisesRegex(Exception,'사용 가능하지'):
            configure_first_nebius_key(self.registry,self.key,lambda:None,get=unavailable)
        self.assertFalse(StageRoutingSettings(self.registry).path.exists())
        self.assertTrue(self.registry.state()['entries'][-1]['configured'])

    def test_refresh_adds_newly_visible_image_models_and_keeps_the_saved_choices(self):
        configure_first_nebius_key(self.registry,self.key,lambda:None,get=self.get)
        def wider(url,credential):
            result,sha=self.get(url,credential)
            if url.endswith('models_info'):
                result[0]['flavors'].append(dict(model_id='nvidia/Nemotron-3_5-Super-VL',use_cases=['text','image'],
                    max_model_len=131072,input_price_per_million_tokens=.2,output_price_per_million_tokens=.6))
            else:result['data'].append(dict(id='nvidia/Nemotron-3_5-Super-VL'))
            return result,'c'*64
        self.calls=[];changed=[]
        result=refresh_model_catalog(self.registry,self.key,lambda:changed.append(True),get=wider)
        self.assertEqual(result['state'],'refreshed');self.assertEqual(len(self.calls),2);self.assertEqual(result['model_count'],3)
        self.assertEqual(result['image_models'],['deepseek-ai/DeepSeek-V4.1-Flash','nvidia/Nemotron-3_5-Super-VL'])
        routes=StageRoutingSettings(self.registry);route=routes.load()
        self.assertEqual(route['observer']['model_id'],'deepseek-ai/DeepSeek-V4.1-Flash')  # the saved choice never moves by itself
        state=routes.state(self.registry.state()['entries'])
        self.assertIn('nvidia/Nemotron-3_5-Super-VL',[o['model_id'] for o in state['options']['observer']])
        self.assertEqual(changed,[True])
        # choosing the new photo model now validates against the fresh pinned catalog
        observer={k:v for k,v in route['observer'].items() if k!='harness_profile'}  # a profile is bound to its model; the UI drops it on a model change
        routes.save(dict(route,observer=dict(observer,model_id='nvidia/Nemotron-3_5-Super-VL')),lambda:None)
        self.assertEqual(routes.load()['observer']['model_id'],'nvidia/Nemotron-3_5-Super-VL')
    def test_refresh_that_drops_the_saved_model_restores_the_previous_list(self):
        configure_first_nebius_key(self.registry,self.key,lambda:None,get=self.get)
        path=StageRoutingSettings(self.registry).path.with_name('stage_model_catalog.json');before=path.read_bytes()
        def narrower(url,credential):
            result,sha=self.get(url,credential)
            if url.endswith('/models'):result={'data':[dict(id='nvidia/nemotron-3-super-120b-a12b')]}
            return result,sha
        with self.assertRaises(Exception):refresh_model_catalog(self.registry,self.key,lambda:None,get=narrower)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(StageRoutingSettings(self.registry).load()['observer']['model_id'],'deepseek-ai/DeepSeek-V4.1-Flash')

if __name__=='__main__':unittest.main()
