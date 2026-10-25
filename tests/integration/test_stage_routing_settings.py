# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Ordinary persisted routing: offline contracts, not model quality/runtime acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from twinpulse_app import LocalApiServer, CommandBroker
from twinpulse_app.key_registry import KeyRegistry, KeyRegistryError
from twinpulse_app.settings import JsonProviderSettingsStore, provider_settings_preset
from twinpulse_app.stage_routing import StageRoutingSettings, build_configured_stage_service, configured_model
from twinpulse_app.command_broker import BrokerError
from twinpulse_provider import CancellationToken, ProviderConfigurationError, GenerationRequest, ImageInput
from twinpulse_provider.nebius_pipeline import ChatCompletion, ObservationArtifact
from twinpulse_provider.stage_transport import ConfiguredStageTransport
from twinpulse_provider.photo_layout import compile_layout, REVISION
from twinpulse_provider.scene_contract import PROPOSAL_REVISION
from twinpulse_core import InputRevision

class Credential:
    secrets = {}
    reads = []
    def __init__(self, target): self.target_name = target
    def load(self):
        self.reads.append(self.target_name)
        return self.secrets.get(self.target_name)
    def is_configured(self): return bool(self.secrets.get(self.target_name))
    def save(self, secret): self.secrets[self.target_name] = secret
    def delete(self): self.secrets.pop(self.target_name, None)


class StageSettingsTests(unittest.TestCase):
    def test_save_and_rollback_callbacks_never_hold_registry_against_snapshot(self):
        from threading import Event,RLock,Thread
        for fail_first in (False,True):
            workflow_lock=RLock();entered=Event();callback_entered=Event();errors=[];seen=[]
            def reader():
                try:
                    with workflow_lock:
                        entered.set()
                        if not callback_entered.wait(2):raise AssertionError('Save never reached callback')
                        self.registry.settings_for_entry('legacy')
                except Exception as error:errors.append(error)
            def changed():
                callback_entered.set()
                with workflow_lock:
                    seen.append(self.routes.load())
                # The rollback callback also must allow another registry reader.
                unlocked=Event()
                thread=Thread(target=lambda:(self.registry.settings_for_entry('legacy'),unlocked.set()),daemon=True)
                thread.start()
                if not unlocked.wait(2):raise AssertionError('Callback retained registry lock')
                thread.join(1)
                if fail_first and len(seen)==1:raise RuntimeError('deliberate local reconstruction failure')
            thread=Thread(target=reader,daemon=True);thread.start();self.assertTrue(entered.wait(1))
            if fail_first:
                with self.assertRaisesRegex(KeyRegistryError,'이전 조합'):
                    self.routes.save(self.route,changed)
            else:self.routes.save(self.route,changed)
            thread.join(2);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            self.assertEqual(len(seen),2 if fail_first else 1)

    def expected_saved_route(self, requested, routes=None):
        """Explicit saves pin model defaults; compare the full specified identity.

        Legacy-wire fixtures opt out with explicit null instead of stripping
        profile fields from assertions or silently accepting any saved digest.
        """
        from twinpulse_provider.harness_profiles import default_profile,binding
        routes=routes or self.routes
        expected=deepcopy(requested)
        for stage in ('observer','planner'):
            choice=expected[stage]
            if 'harness_profile' in choice:continue
            provider=routes.provider(routes.registry.settings_for_entry(choice['key_id']))
            model=configured_model(choice,provider)
            frozen=binding(default_profile(provider,model,stage))
            choice['harness_profile']={key:frozen[key] for key in ('id','revision','sha256')}
            self.assertEqual(routes.harness_store().resolve(choice['harness_profile'],
                provider=provider,model=model,role=stage),frozen)
        return expected

    def test_manifest_isolated_route_does_not_load_global_route_against_fresh_catalog(self):
        from scripts.run_ordinary_staged_live_ten import copy_trial_settings,sha
        from twinpulse_provider.model_contracts import catalog_sha
        catalog=self.install_physical_catalog()
        selected=self.registry.state()['stage_routing']['recommended']
        self.routes.save(selected,lambda:None)
        paths=(self.settings.path,self.registry.path,self.routes.path,
            self.routes.path.with_name('stage_model_catalog.json'))
        original={p:sha(p) for p in paths}
        refreshed=deepcopy(catalog);refreshed['source_sha256']='b'*64
        def isolated(name,manifest_bound):
            target=Path(self.temp.name)/name;target.mkdir()
            copy_trial_settings(self.settings,self.registry,self.routes,target,manifest_bound=manifest_bound)
            (target/'stage_model_catalog.json').write_text(json.dumps(refreshed),encoding='utf-8')
            registry=KeyRegistry(JsonProviderSettingsStore(target/self.settings.path.name),self.legacy,Credential)
            return StageRoutingSettings(registry)
        legacy=isolated('legacy',False)
        with self.assertRaisesRegex(KeyRegistryError,'단계 설정을 읽지 못했습니다'):
            legacy.load()
        trial=isolated('manifest',True)
        self.assertIsNone(trial.load())
        route=deepcopy(selected);route['model_catalog_sha256']=catalog_sha(refreshed)
        trial.save(route,lambda:None)
        self.assertEqual(trial.load(),self.expected_saved_route(route,trial))
        self.assertTrue(all(sha(p)==digest for p,digest in original.items()))
        self.assertEqual(Credential.reads,[])

    def install_physical_catalog(self):
        from datetime import datetime, timedelta, timezone
        from twinpulse_app.stage_routing import PHYSICAL_AI_OBSERVER, PHYSICAL_AI_PLANNER
        now = datetime.now(timezone.utc)
        value = dict(schema_version='stage-model-catalog-1.0',verified_at=now.isoformat(),
            valid_until=(now+timedelta(days=1)).isoformat(),source_sha256='a'*64,models=[
                dict(model_id=model,visible=True,modalities=modalities,context_tokens=131072,
                     input_per_million='0.3',output_per_million='0.9')
                for model,modalities in ((PHYSICAL_AI_OBSERVER,['image','text']),
                                        (PHYSICAL_AI_PLANNER,['text']))])
        self.routes.path.with_name('stage_model_catalog.json').write_text(json.dumps(value),encoding='utf-8')
        return value

    def test_physical_profile_is_exact_unsaved_then_budgeted_and_restored(self):
        from twinpulse_app.stage_routing import PHYSICAL_AI_OBSERVER, PHYSICAL_AI_PLANNER
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        from twinpulse_provider.model_contracts import catalog_sha
        catalog = self.install_physical_catalog()
        state = self.registry.state()['stage_routing']
        selected = state['recommended']
        self.assertFalse(state['enabled'])
        self.assertIsNone(self.routes.load())
        for stage,model in (('observer',PHYSICAL_AI_OBSERVER),('planner',PHYSICAL_AI_PLANNER)):
            self.assertEqual(selected[stage],dict(key_id='legacy',model_id=model,max_output_tokens=40000))
        self.assertEqual(selected['model_catalog_sha256'],catalog_sha(catalog))
        before = self.settings.path.read_bytes()
        self.routes.save(selected,lambda:build_configured_stage_service(self.registry))
        restarted = StageRoutingSettings(KeyRegistry(self.settings,self.legacy,Credential))
        self.assertEqual(restarted.load(),self.expected_saved_route(selected))
        service = build_configured_stage_service(restarted.registry)
        self.assertIsInstance(service._provider,BudgetedPipeline)
        self.assertEqual(service._provider.policy.max_requests,12)
        self.assertEqual(service._provider.policy.max_repairs,3)
        self.assertEqual(service._provider.total_timeout_s,900)
        self.assertEqual(restarted.metadata()['generation_timeout_s'],'300')
        self.assertEqual(service._provider.stage_output_token_caps,dict(observer=40000,planner=40000))
        self.assertEqual(service._provider.planner_model_id,PHYSICAL_AI_PLANNER)
        self.assertFalse(service._provider.planner_template_no_thinking)
        for name in ('initial','repair'):
            body = service._provider.body(name,{'type':'object'},'test',{})
            self.assertEqual(body['model'],PHYSICAL_AI_PLANNER)
            self.assertEqual(body['max_tokens'],40000)
            self.assertNotIn('chat_template_kwargs',body)
        self.assertEqual(self.settings.path.read_bytes(),before)
        self.assertEqual(Credential.reads,[])

    def test_physical_profile_does_not_borrow_other_models_or_legacy_policy(self):
        self.install_physical_catalog()
        selected = self.registry.state()['stage_routing']['recommended']
        for missing in ('generation_policy','model_catalog_sha256'):
            invalid = deepcopy(selected);invalid.pop(missing)
            with self.assertRaises(KeyRegistryError):self.routes.save(invalid,lambda:None)
        invalid = deepcopy(selected);invalid['planner']['thinking_mode']='disabled'
        with self.assertRaises(KeyRegistryError):self.routes.save(invalid,lambda:None)
        # Losing the selected model hides the recommendation, never swaps to Nano.
        path = self.routes.path.with_name('stage_model_catalog.json')
        value = json.loads(path.read_text());value['models'][1]['visible']=False
        path.write_text(json.dumps(value),encoding='utf-8')
        self.assertIsNone(self.registry.state()['stage_routing']['recommended'])
        self.assertIsNone(self.routes.load())
        self.assertEqual(Credential.reads,[])

    def test_recommendation_does_not_overwrite_a_saved_route_and_luna_label_is_exact(self):
        self.routes.save(self.route,lambda:None)
        previous = self.routes.path.read_bytes()
        self.install_physical_catalog()
        state = self.registry.state()['stage_routing']
        self.assertIsNotNone(state['recommended'])
        self.assertEqual(self.routes.path.read_bytes(),previous)
        for stage in ('observer','planner'):
            luna = next(v for v in state['options'][stage] if v['model_id']=='gpt-6-luna')
            self.assertEqual(luna['wire_model_id'],'gpt-6-luna')

    def test_zero_call_cli_applies_profile_and_keeps_previous_route_snapshot(self):
        import scripts.verify_stage_routing_settings as verifier
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        self.install_physical_catalog()
        self.routes.save(self.route,lambda:None)
        previous_settings = self.settings.path.read_bytes()
        previous_keys = self.registry.path.read_bytes()
        captured = StringIO()
        with patch.object(verifier,'WindowsCredentialStore',Credential), \
                patch.object(sys,'argv',['verify','--settings-path',str(self.settings.path),'--apply-physical-ai']), \
                redirect_stdout(captured):
            verifier.main()
        report = json.loads(captured.getvalue())
        self.assertEqual(report['network_calls'],0)
        self.assertEqual(report['composed_whole_generation_timeout_s'],900)
        snapshot = json.loads(Path(report['previous_route_snapshot']).read_text())
        self.assertEqual(snapshot['route'],self.expected_saved_route(self.route))
        self.assertEqual(self.settings.path.read_bytes(),previous_settings)
        self.assertEqual(self.registry.path.read_bytes(),previous_keys)
        self.assertEqual(Credential.reads,[])

    def test_cli_failed_gateway_restores_catalog_and_route(self):
        import scripts.verify_stage_routing_settings as verifier
        self.install_physical_catalog()
        self.routes.save(self.route,lambda:None)
        previous = self.routes.path.read_bytes()
        catalog_path = self.routes.path.with_name('stage_model_catalog.json')
        previous_catalog = catalog_path.read_bytes()
        with patch.object(verifier,'WindowsCredentialStore',Credential), \
                patch.object(verifier,'build_configured_stage_service',side_effect=RuntimeError('fixture failure')), \
                patch.object(sys,'argv',['verify','--settings-path',str(self.settings.path),'--apply-physical-ai']):
            with self.assertRaises(RuntimeError):verifier.main()
        self.assertEqual(self.routes.load(),self.expected_saved_route(self.route))
        self.assertEqual(catalog_path.read_bytes(),previous_catalog)
        self.assertEqual(self.routes.path.read_bytes(),previous)
        self.assertEqual(Credential.reads,[])

    def test_catalog_digest_is_non_secret_input_identity_and_cannot_be_an_arbitrary_value(self):
        values=dict(model_id='test/model',model_catalog_sha256='a'*64)
        revision=InputRevision.create(prompt='text',images=(),generation_settings=values,measurement_constraints=(),profile_id='offline')
        self.assertEqual(InputRevision.from_dict(revision.to_dict()),revision)
        values['model_catalog_sha256']='b'*64
        changed=InputRevision.create(prompt='text',images=(),generation_settings=values,measurement_constraints=(),profile_id='offline')
        self.assertNotEqual(changed.digest,revision.digest)
        for invalid in ('not-a-digest','https://private/path','SECRET'):
            values['model_catalog_sha256']=invalid
            with self.assertRaises(ValueError):InputRevision.create(prompt='text',images=(),generation_settings=values,measurement_constraints=(),profile_id='offline')
            record=revision.to_dict();record['generation_settings']={**record['generation_settings'],'model_catalog_sha256':invalid}
            with self.assertRaises(ValueError):InputRevision.from_dict(record)

    def test_catalog_route_uses_ordinary_gateway_and_preserves_global_defaults_and_secrets(self):
        from twinpulse_provider.model_contracts import catalog_sha
        from twinpulse_provider.generation_policy import GenerationPolicy
        value=dict(schema_version='stage-model-catalog-1.0',verified_at='2026-10-10T00:00:00+00:00',
            valid_until='2026-10-16T00:00:00+00:00',source_sha256='a'*64,models=[
                dict(model_id=name,visible=True,modalities=modalities,context_tokens=32000,
                     input_per_million='0.1',output_per_million='0.2') for name,modalities in
                (('test/vision',['image','text']),('test/plan',['text']),('test/embedding',[]))])
        route={'observer':{'key_id':'legacy','model_id':'test/vision'},
            'planner':{'key_id':'legacy','model_id':'test/plan'},'model_catalog_sha256':catalog_sha(value),
            'generation_policy':GenerationPolicy().to_dict()}
        before=self.settings.path.read_bytes()
        with self.assertRaisesRegex(KeyRegistryError,'동결'):self.routes.validate(route)
        path=self.routes.path.with_name('stage_model_catalog.json');path.write_text(json.dumps(value),encoding='utf-8')
        self.routes.save(route,lambda:None)
        service=build_configured_stage_service(self.registry)
        self.assertEqual(service._provider._transport.configs['planner'].model_id,'test/plan')
        self.assertEqual(self.routes.metadata()['model_catalog_sha256'],catalog_sha(value))
        options=self.registry.state()['stage_routing']['options']
        self.assertEqual({r['model_id'] for r in options['observer'] if r['provider']=='nebius'},{'test/vision'})
        self.assertEqual({r['model_id'] for r in options['planner'] if r['provider']=='nebius'},{'test/vision','test/plan'})
        self.assertEqual(self.settings.path.read_bytes(),before);self.assertEqual(Credential.reads,[])
        above_context=deepcopy(route);above_context['planner']['max_output_tokens']=40000
        with self.assertRaises(KeyRegistryError) as caught:self.routes.validate(above_context)
        self.assertEqual(caught.exception.code,'stage_output_context_invalid')
        self.assertEqual(Credential.reads,[])
        bad=deepcopy(route);bad['observer']['model_id']='test/plan'
        with self.assertRaises(KeyRegistryError):self.routes.validate(bad)
        bad=deepcopy(route);bad.pop('generation_policy')
        with self.assertRaisesRegex(KeyRegistryError,'별도 생성'):self.routes.validate(bad)
        value['models'][0]['context_tokens']=64000;path.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaises(KeyRegistryError):build_configured_stage_service(self.registry)

    def setUp(self):
        (ROOT/'artifacts'/'test-tmp').mkdir(parents=True, exist_ok=True)
        self.temp = TemporaryDirectory(dir=ROOT/'artifacts'/'test-tmp')
        self.addCleanup(self.temp.cleanup)
        self.settings = JsonProviderSettingsStore(Path(self.temp.name)/'settings.json')
        self.settings.save(provider_settings_preset('nebius_token_factory'))
        Credential.secrets = {self.settings.load().credential_ref: 'nebius-canary'}
        Credential.reads = []
        self.legacy = Credential(self.settings.load().credential_ref)
        self.registry = KeyRegistry(self.settings, self.legacy, Credential)
        self.gpt = self.registry.register({'name':'GPT', 'provider_profile':'openai',
            'model_id':'gpt-5.4-mini', 'api_key':'gpt-canary'})['entries'][-1]['id']
        self.routes = StageRoutingSettings(self.registry)
        self.route = {'observer': {'key_id': self.gpt, 'model_id': 'gpt-5.4-mini'},
            'planner': {'key_id': 'legacy', 'model_id': 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'}}

    def test_recommended_not_applied_until_saved_and_restart_preserves_keys(self):
        state = self.registry.state()['stage_routing']
        self.assertFalse(state['enabled'])
        self.assertIsNone(state['recommended'])  # missing reviewed Flash/Super catalog, no fallback
        self.assertIsNone(build_configured_stage_service(self.registry))
        before = self.settings.path.read_bytes()
        self.routes.save(self.route, lambda: build_configured_stage_service(self.registry))
        restarted = KeyRegistry(self.settings, self.legacy, Credential)
        self.assertEqual(StageRoutingSettings(restarted).load(), self.expected_saved_route(self.route))
        self.assertEqual(self.settings.path.read_bytes(), before)
        for text in (self.routes.path.read_text(), json.dumps(self.registry.state()), json.dumps(self.routes.metadata())):
            self.assertNotIn('gpt-canary', text)
            self.assertNotIn('nebius-canary', text)
        self.assertEqual(Credential.reads, [])
        metadata = self.routes.metadata()
        revision = InputRevision.create(prompt='test', images=(), generation_settings=metadata,
            measurement_constraints=(), profile_id='offline')
        self.assertEqual(revision.generation_settings['observer_base_url'], 'https://api.openai.com/v1/')

    def test_benchmark_alternates_preserve_exact_models_and_luna_wire_mode(self):
        from twinpulse_app.generation_approval import REVIEWED_PRICES
        for observer,planner in (('Qwen/Qwen3.8-27B','nvidia/Nemotron-3_5-Lightning'),
                                ('gpt-6-luna','gpt-6-luna'),
                                ('gpt-6-luna','nvidia/Nemotron-3_5-Lightning')):
            route={'observer':{'key_id':self.gpt if observer=='gpt-6-luna' else 'legacy','model_id':observer},
                'planner':{'key_id':self.gpt if planner=='gpt-6-luna' else 'legacy','model_id':planner}}
            self.routes.save(route,lambda:None)
            service=build_configured_stage_service(self.registry)
            transport=service._provider._transport
            metadata=self.routes.metadata()
            self.assertEqual(metadata['observer_model_id'],observer)
            self.assertEqual(metadata['model_id'],planner)
            for stage,model in (('observer',observer),('planner',planner)):
                self.assertEqual(transport.configs[stage].model_id,model)
                self.assertIn(model,REVIEWED_PRICES)
                if model=='gpt-6-luna':self.assertEqual(transport.reasoning[stage],'none')
            self.assertEqual(Credential.reads,[])

    def test_explicit_no_thinking_persists_and_initial_and_repair_wire_match(self):
        service, request, calls = self.scripted_service()
        route = self.routes.load()
        route['planner']['thinking_mode'] = 'disabled'
        self.routes.save(route, lambda: None)
        replacement = build_configured_stage_service(self.registry)
        service._provider.planner_template_no_thinking = replacement._provider.planner_template_no_thinking
        asyncio.run(service.generate(request))
        planner_calls = [body for body, _config, _key in calls if body['model'] == service._config.model_id]
        self.assertEqual(len(planner_calls), 2)
        self.assertTrue(all(body['chat_template_kwargs'] == {'enable_thinking': False} for body in planner_calls))
        self.assertTrue(all(body['max_tokens'] == 20000 for body in planner_calls))
        self.assertEqual(self.routes.metadata()['planner_thinking_mode'], 'disabled')
        # Unsupported combinations fail before save or any request.
        for changed in ('observer', 'planner'):
            invalid = deepcopy(route)
            invalid[changed] = {'key_id': self.gpt, 'model_id': 'gpt-5.4-mini', 'thinking_mode': 'disabled'}
            with self.assertRaises(KeyRegistryError): self.routes.save(invalid, lambda: None)
        self.assertEqual(self.routes.load(), route)

    def test_new_policy_is_explicit_legacy_timeout_and_host_scope_unchanged(self):
        from twinpulse_provider.generation_policy import GenerationPolicy
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        legacy = {**self.route, 'generation_timeout_s': 300}
        self.routes.save(legacy, lambda: None)
        previous_metadata = self.routes.metadata()
        self.assertNotIn('generation_policy_sha256', previous_metadata)
        self.assertEqual(build_configured_stage_service(self.registry)._config.timeout_s, 300)
        selected = {**legacy, 'generation_policy': GenerationPolicy().to_dict()}
        self.routes.save(selected, lambda: None)
        service = build_configured_stage_service(self.registry)
        self.assertIsInstance(service._provider, BudgetedPipeline)
        self.assertEqual(service._provider.total_timeout_s, 900)
        self.assertEqual(service._config.timeout_s, 300)
        InputRevision.create(prompt='policy check', images=(), measurement_constraints=(),
            profile_id='test', generation_settings=self.routes.metadata())
        with self.assertRaises(ProviderConfigurationError):
            build_configured_stage_service(self.registry, campaign=object())
        self.assertEqual(self.routes.load(), self.expected_saved_route(selected))

    def test_reviewed_nebius_combination_builds_budgeted_gateway_without_dispatch(self):
        from twinpulse_provider.generation_policy import GenerationPolicy
        from twinpulse_app.generation_approval import REVIEWED_PRICES
        selected={'observer':{'key_id':'legacy','model_id':'deepseek-ai/DeepSeek-V4.1-Flash','max_output_tokens':20000},
            'planner':{'key_id':'legacy','model_id':'nvidia/Nemotron-3_5-Lightning',
                       'max_output_tokens':20000,'thinking_mode':'disabled'},
            'generation_policy':replace(GenerationPolicy(),max_requests=10,external_final_review=True).to_dict()}
        self.routes.save(selected,lambda:None)
        service=build_configured_stage_service(self.registry)
        self.assertEqual(service._provider.observer_model_id,selected['observer']['model_id'])
        self.assertEqual(service._provider.planner_model_id,selected['planner']['model_id'])
        self.assertTrue(service._provider.planner_template_no_thinking)
        self.assertTrue(service._provider.policy.external_final_review)
        for stage in ('observer','planner'):
            self.assertIn(selected[stage]['model_id'],REVIEWED_PRICES)
            self.assertTrue(any(v['model_id']==selected[stage]['model_id'] for v in self.registry.state()['stage_routing']['options'][stage]))
        invalid=deepcopy(selected);invalid['observer']['model_id']='nvidia/Nemotron-3_5-Lightning'
        with self.assertRaises(KeyRegistryError):self.routes.save(invalid,lambda:None)
        self.assertEqual(self.routes.load(),self.expected_saved_route(selected))

    def test_supported_combinations_and_bad_choices_do_not_change_saved_route(self):
        for observer_key, observer_model, planner_key, planner_model in (
            (self.gpt, 'gpt-5.4-mini', 'legacy', self.route['planner']['model_id']),
            ('legacy', 'google/gemma-3-27b-it', 'legacy', self.route['planner']['model_id']),
            ('legacy', 'openbmb/MiniCPM-V-4_5', self.gpt, 'gpt-5.4-mini'),
            (self.gpt, 'gpt-5.4-mini', self.gpt, 'gpt-5.4-mini')):
            value = {'observer': {'key_id':observer_key,'model_id':observer_model},
                'planner': {'key_id':planner_key,'model_id':planner_model}}
            self.routes.save(value, lambda: build_configured_stage_service(self.registry))
        before = self.routes.path.read_bytes()
        for mutation in ({'model_id':'unsupported'}, {'key_id':'missing'},
                {'model_id':'google/gemma-3-27b-it'}, {'extra':'secret'}):
            value = deepcopy(self.route); value['planner'].update(mutation)
            with self.assertRaises(KeyRegistryError): self.routes.save(value, lambda: None)
            self.assertEqual(self.routes.path.read_bytes(), before)

    def test_failed_gateway_rebuild_rolls_back_and_busy_api_rejects(self):
        calls = []
        def failed():
            calls.append(self.routes.load())
            if self.routes.load(): raise RuntimeError('gpt-canary')
        with self.assertRaises(KeyRegistryError) as caught: self.routes.save(self.route, failed)
        self.assertEqual(caught.exception.code, 'stage_switch_failed')
        self.assertNotIn('gpt-canary', str(caught.exception))
        self.assertIsNone(self.routes.load()); self.assertEqual(len(calls), 2)
        server = self.server()
        server.product_workflow = SimpleNamespace(snapshot=lambda: {'phase':'generating'})
        with self.assertRaises(BrokerError) as caught:
            server._provider_keys({'action':'stage_routing','route':self.route})
        self.assertEqual(caught.exception.code, 'generation_busy')
        self.assertIsNone(self.routes.load())

    def server(self):
        server = LocalApiServer(CommandBroker(), product_bootstrap_secret='p'*40, engine_bootstrap_secret='e'*40,
            provider_settings_store=self.settings, credential_store=self.legacy, key_registry=self.registry)
        self.addCleanup(server._httpd.server_close)
        return server

    def test_api_applies_route_to_generation_gateway_and_pins_keys(self):
        server = self.server(); services = []
        server.product_workflow = SimpleNamespace(snapshot=lambda: {'phase':'empty'}, has_active_generation=lambda:False,
            provider_settings_changed=lambda: services.append(build_configured_stage_service(self.registry)))
        state = server._provider_keys({'action':'stage_routing','route':self.route})
        self.assertTrue(state['stage_routing']['enabled']); self.assertIsNotNone(services[-1])
        self.assertTrue(all(entry['stage_selected'] for entry in state['entries']))
        with self.assertRaises(KeyRegistryError): self.registry.remove(self.gpt)
        with self.assertRaises(KeyRegistryError): self.registry.select(self.gpt, lambda:None)
        server._provider_keys({'action':'stage_routing','route':None})
        self.assertIsNone(services[-1]); self.registry.select(self.gpt, lambda:None)

    def test_missing_credential_corrupt_file_and_foreign_origin_fail_closed(self):
        self.routes.save(self.route, lambda:None)
        Credential.secrets.pop(self.registry.settings_for_entry(self.gpt).credential_ref)
        with self.assertRaises(KeyRegistryError): build_configured_stage_service(self.registry)
        self.assertEqual(self.routes.load(), self.expected_saved_route(self.route))
        self.routes.path.write_text('{invalid', encoding='utf-8')
        with self.assertRaises(KeyRegistryError): self.routes.load()
        self.assertEqual(self.routes.path.read_text(), '{invalid')
        with self.assertRaises(ProviderConfigurationError): build_configured_stage_service(self.registry, campaign=object())

    def scripted_service(self, *, text=False, reverse=False):
        route = deepcopy(self.route)
        if reverse:
            route = {'observer': {'key_id':'legacy','model_id':'google/gemma-3-27b-it'},
                     'planner': {'key_id':self.gpt,'model_id':'gpt-5.4-mini'}}
        # These fixtures test the pre-profile wire/repair/credential contract.
        # New snapshot composition is covered by test_model_harness_integration.
        for stage in ('observer','planner'):route[stage]['harness_profile']=None
        self.routes.save(route, lambda:None)
        request = GenerationRequest('ordinary-stage-test', 'Create a bedroom with a bed.',
            () if text else (ImageInput('test.jpg','image/jpeg',b'offline'),))
        observation = {'schema_version':'1.0','summary':'Approximate bed.',
            'entities':[{'id':'bed_visual','kind':'static_obstacle','description':'bed','confidence':.5}],
            'relations':[],'dimensions':[],'ambiguities':['Scale unmeasured']}
        layout = {'layout_version':REVISION, 'summary':'Estimated bedroom.',
            'room':{'width_m':4,'length_m':5,'height_m':2.5},
            'objects':[{'id':'bed','kind':'bed','region':'middle_right','yaw_deg':0,'observation_ids':['bed_visual']}]}
        plan, _ = compile_layout(layout, ObservationArtifact.from_mapping(observation), request, None)
        if text:
            for evidence in plan['call_evidence']:
                evidence.update(basis='user',observation_ids=[], user_quote=request.prompt)
        calls = deepcopy(plan['calls']); evidence = deepcopy(plan['call_evidence'])
        for item in evidence:
            item['user_quote'] = request.prompt if item['basis']=='user' else None
        floor = next(c for c in calls if c['tool']=='create_floor')
        floor_evidence = next(e for e in evidence if e['call_id']==floor['call_id'])
        proposal = {**{k:deepcopy(plan[k]) for k in ('plan_version','scene_id','summary','image_observations')},
            'proposal_version':PROPOSAL_REVISION, 'coordinate_frame':'local_xy' if text else 'photo_view_right_rear',
            'floor_call':floor,'floor_evidence':floor_evidence,
            'scene_calls':[c for c in calls if c is not floor],
            'call_evidence':[e for e in evidence if e is not floor_evidence]}
        recorded = []
        class Scripted:
            def __init__(self, getter, evidence): self.getter = getter; self.plans = 0
            async def complete(self, body, token, config):
                recorded.append((deepcopy(body), config, self.getter()))
                observer = body['response_format']['json_schema']['name']=='twinpulse_image_observation'
                if not observer: self.plans += 1
                value = observation if observer else ({} if self.plans==1 else proposal)
                return ChatCompletion(str(len(recorded)),config.model_id,json.dumps(value),'stop',{})
        with patch('twinpulse_provider.reliability.AuditedChatTransport', Scripted):
            service = build_configured_stage_service(self.registry)
        return service, request, recorded

    def test_photo_pipeline_uses_correct_credentials_and_repairs_without_image_leak(self):
        service, request, calls = self.scripted_service()
        asyncio.run(service.generate(request))
        self.assertEqual(len(calls), 3)
        self.assertEqual([c[2] for c in calls], ['gpt-canary','nebius-canary','nebius-canary'])
        self.assertIn('data:image/', json.dumps(calls[0][0]))
        self.assertIn('max_completion_tokens', calls[0][0])
        self.assertTrue(all('data:image/' not in json.dumps(c[0]) for c in calls[1:]))
        self.assertEqual(service._provider.diagnostic_for(request.request_id)['repair_count'], 1)

    def test_output_limits_persist_validate_wire_and_change_input_revision(self):
        self.routes.save(self.route, lambda:None)
        old = self.routes.metadata()
        self.assertEqual(old['planner_max_output_tokens'], '20000')
        self.assertEqual(self.registry.state()['stage_routing']['max_output_tokens'],40000)
        for cap in (0, 40001, True, 2.5, '20000'):
            route = deepcopy(self.route); route['planner']['max_output_tokens'] = cap
            before = self.routes.path.read_bytes()
            with self.assertRaises(KeyRegistryError):self.routes.save(route, lambda:None)
            self.assertEqual(before, self.routes.path.read_bytes())
        route = deepcopy(self.route)
        route['observer']['max_output_tokens'] = 5000
        route['planner']['max_output_tokens'] = 40000
        self.routes.save(route, lambda:build_configured_stage_service(self.registry))
        self.assertEqual(StageRoutingSettings(KeyRegistry(self.settings,self.legacy,Credential)).load(), self.expected_saved_route(route))
        revised = self.routes.metadata()
        self.assertNotEqual(InputRevision.create(prompt='test',images=(),measurement_constraints=(),profile_id='test',generation_settings=old).digest,
            InputRevision.create(prompt='test',images=(),measurement_constraints=(),profile_id='test',generation_settings=revised).digest)
        service, request, calls = self.scripted_service()
        service._provider.stage_output_token_caps = {'observer':5000,'planner':40000}
        asyncio.run(service.generate(request))
        self.assertEqual(calls[0][0]['max_completion_tokens'],5000)
        self.assertEqual([c[0]['max_tokens'] for c in calls[1:]], [40000,40000])

    def test_total_timeout_persists_rebuilds_gateway_and_preserves_legacy_default(self):
        self.routes.save(self.route, lambda:None)
        old = self.routes.metadata()
        self.assertEqual(old['generation_timeout_s'], '90')
        self.assertEqual(build_configured_stage_service(self.registry)._config.timeout_s, 90.)
        before = self.routes.path.read_bytes()
        for timeout in (0, 301, True, 2.5, '300', None):
            with self.assertRaises(KeyRegistryError) as caught:
                self.routes.save({**self.route,'generation_timeout_s':timeout}, lambda:None)
            self.assertEqual(caught.exception.code,'stage_timeout_invalid')
            self.assertEqual(before,self.routes.path.read_bytes())
        route = {**self.route,'generation_timeout_s':300}
        server = self.server()
        state = server._provider_keys({'action':'stage_routing','route':route})
        self.assertEqual(state['stage_routing']['route'],self.expected_saved_route(route))
        self.assertTrue(all(entry['stage_selected'] for entry in state['entries']))
        with self.assertRaises(KeyRegistryError):self.registry.remove(self.gpt)
        restarted = KeyRegistry(self.settings,self.legacy,Credential)
        self.assertEqual(StageRoutingSettings(restarted).load(),self.expected_saved_route(route))
        service = build_configured_stage_service(restarted)
        self.assertEqual(service._config.timeout_s,300.)
        self.assertTrue(all(config.timeout_s==300. for config in service._provider._transport.configs.values()))
        revised = self.routes.metadata()
        self.assertEqual(revised['generation_timeout_s'],'300')
        self.assertNotEqual(InputRevision.create(prompt='test',images=(),measurement_constraints=(),profile_id='test',generation_settings=old).digest,
            InputRevision.create(prompt='test',images=(),measurement_constraints=(),profile_id='test',generation_settings=revised).digest)
        self.assertEqual(Credential.reads,[])
        def fail_on_new():
            if self.routes.load().get('generation_timeout_s')==120:raise RuntimeError('rebuild failed')
        with self.assertRaises(KeyRegistryError):self.routes.save({**route,'generation_timeout_s':120},fail_on_new)
        self.assertEqual(self.routes.load(),self.expected_saved_route(route))

    def test_five_call_host_scope_binds_saved_limits_without_expanding_old_scopes(self):
        from twinpulse_app import split_evaluation as module
        route=deepcopy(self.route);route['planner']['max_output_tokens']=20000
        for stage in ('observer','planner'):route[stage]['harness_profile']=None
        self.routes.save(route,lambda:None)
        root=Path(self.temp.name);campaign=root/'campaign.json';path=root/'scope.json'
        scope=dict(schema_version='configured-stage-evaluation-1.0',approval='explicit offline fixture',
            max_requests=5,limit_usd='0.15',campaign_path=str(campaign.resolve()),
            observer_entry_id=self.gpt,planner_entry_id='legacy',
            observer_settings=self.registry.settings_for_entry(self.gpt).to_dict(),
            planner_settings=self.settings.load().to_dict(),observer_model=module.OPENAI_MINI_SNAPSHOT,planner_model=module.NANO,
            saved_stage_route=route,stage_output_tokens={'observer':4000,'planner':20000},
            rates={module.OPENAI_MINI_SNAPSHOT:dict(input_per_million='0.75',output_per_million='4.50',context_tokens=400000,
                source='https://developers.openai.com/api/docs/models/gpt-5.4-mini'),
                module.NANO:dict(input_per_million='.06',output_per_million='.24',context_tokens=262144,
                    source='https://api.tokenfactory.nebius.com/private/v1/models_info')})
        path.write_text(json.dumps(scope),encoding='utf-8')
        with patch.object(module,'KeyRegistry',lambda *args:self.registry),patch.object(module,'WindowsCredentialStore',lambda:self.legacy):
            bundle=module.load_evaluation_scope(path,campaign,request_cap=3)
            self.assertEqual(bundle[-1].state['max_requests'],5)
            with self.assertRaises(ProviderConfigurationError):
                module.build_scoped_split_service(*bundle,evidence_root=root/'evidence')
            for mutation in ({'schema_version':'mixed-evaluation-1.0'},
                             {'stage_output_tokens':{'observer':4000,'planner':8000}}, {'max_requests':11},
                             {'generation_timeout_s':300}, {'generation_timeout_s':True}):
                path.write_text(json.dumps({**scope,**mutation}),encoding='utf-8')
                with self.assertRaises(ProviderConfigurationError):module.load_evaluation_scope(path,campaign,request_cap=3)
            route['generation_timeout_s']=300
            self.routes.save(route,lambda:None)
            scope.update(saved_stage_route=route,generation_timeout_s=300)
            path.write_text(json.dumps(scope),encoding='utf-8')
            self.assertEqual(module.load_evaluation_scope(path,campaign,request_cap=3)[0]['generation_timeout_s'],300)
            path.write_text(json.dumps({**scope,'generation_timeout_s':90}),encoding='utf-8')
            with self.assertRaises(ProviderConfigurationError):module.load_evaluation_scope(path,campaign,request_cap=3)
        self.assertEqual(json.loads(campaign.read_text())['requests'],[])

    def test_truncated_observer_or_planner_stops_without_repair(self):
        from twinpulse_provider import InvalidProviderResponseError
        from twinpulse_provider.nebius_pipeline import parse_chat_completion
        for stage, content in (('observer',None), ('observer','{"partial":'), ('planner',None),('planner','{"partial":')):
            service, request, calls = self.scripted_service()
            ordinary = service._provider._transport.complete
            async def truncated(body, token, config):
                current = 'observer' if body['response_format']['json_schema']['name']=='twinpulse_image_observation' else 'planner'
                if current == stage:
                    calls.append((deepcopy(body),config,'not-a-real-key'))
                    return parse_chat_completion({'id':'length','model':body['model'],
                        'choices':[{'finish_reason':'length','message':{'content':content,'reasoning':'not a plan'}}],
                        'usage':{'prompt_tokens':10,'completion_tokens':20000,'total_tokens':20010}})
                return await ordinary(body,token,config)
            service._provider._transport.complete = truncated
            with self.assertRaises(InvalidProviderResponseError) as error:
                asyncio.run(service.generate(request))
            self.assertEqual(error.exception.code, 'PROVIDER_OUTPUT_TRUNCATED')
            self.assertEqual(len(calls),1 if stage=='observer' else 2)
            diagnostic=service._provider.diagnostic_for(request.request_id)
            self.assertEqual(diagnostic['repair_count'],0)
            self.assertEqual(diagnostic['stop_reason'],'output_limit_reached')

    def test_text_skips_observer_and_reverse_combination_changes_real_dispatch(self):
        for text, reverse in ((True, False), (False, True)):
            service, request, calls = self.scripted_service(text=text, reverse=reverse)
            asyncio.run(service.generate(request))
            self.assertEqual(len(calls), 2 if text else 3)
            self.assertEqual(calls[-1][2], 'gpt-canary' if reverse else 'nebius-canary')
            self.assertEqual('max_completion_tokens' in calls[-1][0], reverse)

    def test_dispatch_rejects_tampered_model_image_leak_and_unknown_stage(self):
        service, _, calls = self.scripted_service()
        transport = service._provider._transport
        body = {'model':service._config.model_id, 'response_format':{'json_schema':{'name':'twinpulse_site_tool_plan_v2'}},
            'messages':[{'role':'user','content':'data:image/jpeg;base64,fixture'}]}
        for mutation in ({}, {'model':'unknown'}, {'response_format':{'json_schema':{'name':'unknown'}}}):
            with self.assertRaises(ProviderConfigurationError):
                asyncio.run(transport.complete({**body,**mutation}, CancellationToken(), service._config))
        self.assertFalse(calls)
        configs = dict(transport.configs)
        configs['observer'] = replace(configs['observer'], base_url='https://evil.example/v1/')
        with self.assertRaises(ProviderConfigurationError):
            ConfiguredStageTransport(transport.transports, configs, transport.providers, transport.reasoning)

    def test_environment_photo_schema_routes_only_to_observer(self):
        service,_,calls=self.scripted_service()
        from twinpulse_provider.harness_profiles import binding,default_profile
        transport=service._provider._transport
        transport.harness_bindings={'observer':binding(default_profile(transport.providers['observer'],service._provider.observer_model_id,'observer'))}
        body={'model':service._provider.observer_model_id,'max_tokens':1000,
            'response_format':{'type':'json_schema','json_schema':{'name':'twinpulse_environment_photo','strict':True,'schema':{'type':'object','properties':{},'additionalProperties':False}}},
            'messages':[{'role':'system','content':'Return the supplied observation contract.'},
                {'role':'user','content':[{'type':'text','text':'Inspect this photo.'},{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,fixture'}}]}]}
        asyncio.run(service._provider._transport.complete(body,CancellationToken(),service._config))
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][2],'gpt-canary')
        self.assertIn('Model-specific guidance',calls[0][0]['messages'][0]['content'])

    def test_http_route_mutation_requires_cookie_csrf_and_reconstructs_gateway(self):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        server = self.server(); applied = []
        server.product_workflow = SimpleNamespace(snapshot=lambda:{'phase':'empty'},has_active_generation=lambda:False,
            provider_settings_changed=lambda: applied.append(build_configured_stage_service(self.registry)), shutdown=lambda:None)
        server.start(); self.addCleanup(server.stop)
        def request(path, body, headers=None):
            req = Request(server.base_url+path, data=json.dumps(body).encode(),
                headers={'Content-Type':'application/json', **(headers or {})})
            try:
                with urlopen(req, timeout=3) as response:
                    return response.status, json.loads(response.read()), response.headers
            except HTTPError as error:
                return error.code, json.loads(error.read()), error.headers
        body = {'action':'stage_routing','route':self.route}; path = '/v1/product/provider-keys'
        self.assertEqual(request(path, body)[0], 401)
        _, session, headers = request('/v1/bootstrap', {'role':'product','secret':'p'*40})
        cookie = {'Cookie':headers['Set-Cookie'].split(';')[0]}
        self.assertEqual(request(path, body, cookie)[0], 403)
        status, value, _ = request(path, body, {**cookie, 'X-TwinPulse-CSRF':session['csrf_token']})
        self.assertEqual(status, 200); self.assertTrue(value['stage_routing']['enabled'])
        self.assertEqual(len(applied), 1)
        self.assertNotIn('gpt-canary', json.dumps(value)); self.assertEqual(Credential.reads, [])

    def test_budgeted_backend_start_handles_policy_metadata_without_treating_it_as_a_key(self):
        from twinpulse_provider.generation_policy import GenerationPolicy
        self.route['generation_policy']=GenerationPolicy().to_dict()
        self.test_ordinary_backend_start_reads_saved_route_and_settings_change_invalidates_input()

    def test_ordinary_backend_start_reads_saved_route_and_settings_change_invalidates_input(self):
        import importlib.util
        import os
        import socket
        import signal
        self.routes.save(self.route, lambda:None)
        spec = importlib.util.spec_from_file_location('stage_backend_test', ROOT/'scripts'/'twinpulse_backend.py')
        backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
        captured = []
        class Server:
            port = 1
            base_url = 'http://127.0.0.1:1'
            def __init__(self, *args, **kwargs): captured.append(kwargs['product_workflow'])
            def start(self): pass
            def stop(self): pass
        class Done:
            def wait(self, _time): return True
            def set(self): pass
        argv = ['backend', '--settings-path', str(self.settings.path), '--static-root', str(Path(self.temp.name)),
            '--ready-file', str(Path(self.temp.name)/'ready.json'), '--session-history-root', self.temp.name]
        with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'TWINPULSE_PRODUCT_BOOTSTRAP':'p'*40,
                'TWINPULSE_ENGINE_BOOTSTRAP':'e'*40}), patch.object(backend, 'WindowsCredentialStore', Credential), \
                patch.object(backend, 'KeyRegistry', lambda settings, legacy:KeyRegistry(settings,legacy,Credential)), \
                patch.object(backend, 'LocalApiServer', Server), patch.object(backend, 'Event', Done), \
                patch.object(backend, 'RobotDiagnostics', lambda *args:None), \
                patch.object(backend, 'RobotReadiness', lambda *args:None), \
                patch.object(backend, 'PhysicalController', lambda *args:None), \
                patch.object(signal, 'signal'), patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
            self.assertEqual(backend.main(), 0)
        workflow = captured[0]
        self.addCleanup(workflow.shutdown)
        self.assertIn('saved stage settings', workflow.snapshot()['provider']['label'])
        input_body = {'prompt':'Create a bedroom with a bed.', 'input_kind':'auto', 'name':None, 'media_type':None,
                      'content_base64':None, 'sidecar_name':None, 'sidecar_content_base64':None}
        workflow.select_input(input_body)
        before = workflow.snapshot()['input']
        reversed_route = {'observer':self.route['observer'], 'planner':{'key_id':self.gpt,'model_id':'gpt-5.4-mini'}}
        self.routes.save(reversed_route, workflow.provider_settings_changed)
        self.assertIsNone(workflow.snapshot()['input'])
        self.assertEqual(workflow.snapshot()['phase'], 'empty')
        workflow.select_input(input_body)
        after = workflow.snapshot()['input']
        self.assertNotEqual(before['revision'], after['revision'])
        self.assertEqual(workflow._generation_settings_getter()['model_id'], 'gpt-5.4-mini-2026-03-17')
        self.assertEqual(Credential.reads, [])

if __name__ == '__main__': unittest.main()
