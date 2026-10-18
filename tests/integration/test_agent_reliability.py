# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Real pipeline/executor and bounded transport; injected network, no hardware."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import urllib.error
from threading import Event
import time

from tests.integration.test_chat_site_text_generation import room, shell_observation
from packages.twinpulse_provider.tests.test_nebius_pipeline import (
    ScriptedTransport, completion, config, request, observation, OBSERVER_MODEL, PLANNER_MODEL)
from twinpulse_provider import (GenerationRequest, GenerationService, CancellationToken,
    InvalidProviderResponseError, ProviderTimeoutError, ProviderAuthenticationError, ProviderRequestError,
    ProviderConfigurationError, NebiusChatCompletionsPipelineProvider)
from twinpulse_provider.reliability import CampaignLedger, InferenceEvidence, AuditedChatTransport, safe_text
from twinpulse_app.product_workflow_service import _public_generation_diagnostics


def adapter(transport, repairs=1):
    return NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
        planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=repairs)


class RepairTests(unittest.IsolatedAsyncioTestCase):
    def test_default_product_keeps_thinking_and_named_dimensions_are_not_positions(self):
        from twinpulse_provider.nebius_pipeline import ObservationArtifact
        provider=adapter(ScriptedTransport())
        empty=ObservationArtifact.from_mapping(dict(schema_version='1.0',summary='Text only',
            entities=[],relations=[],dimensions=[],ambiguities=['Unmeasured']))
        body=provider.build_planner_body(GenerationRequest('x','Bedroom'),empty)
        self.assertNotIn('extra_body',body)
        self.assertNotIn('reasoning_effort',body)
        payload=json.loads(body['messages'][1]['content'])
        self.assertEqual(set(payload['furniture_dimensions_at_zero_yaw_m']['bed']),{'width_x_m','depth_y_m'})

    def test_reasoning_only_json_is_never_promoted_to_scene_content(self):
        from twinpulse_provider.nebius_pipeline import parse_chat_completion
        with self.assertRaisesRegex(InvalidProviderResponseError,'content is missing'):
            parse_chat_completion(dict(id='x',model=PLANNER_MODEL,choices=[dict(finish_reason='stop',
                message=dict(content=None,reasoning=json.dumps(room())))],usage={}))

    def test_live_site_version_is_a_non_secret_revision_setting(self):
        from twinpulse_core import InputRevision
        kwargs=dict(prompt='Bedroom', images=(), measurement_constraints=(), profile_id='burger',
                    generation_settings={'provider_profile':'nebius_token_factory','site_plan_version':'2.2'})
        revision=InputRevision.create(**kwargs)
        self.assertEqual(InputRevision.from_dict(revision.to_dict()), revision)
        kwargs['generation_settings']={'api_key':'must-not-persist'}
        with self.assertRaises(ValueError):InputRevision.create(**kwargs)

    async def text(self, transport):
        provider=adapter(transport)
        result=await GenerationService(provider,config(timeout_s=10),plan_version='2.2').generate(
            GenerationRequest('repair-job','Create a bedroom'))
        return provider,result

    async def test_json_repair_uses_same_input_schema_and_one_extra_request(self):
        bad=completion('bad',PLANNER_MODEL,room())
        from dataclasses import replace
        transport=ScriptedTransport(replace(bad,content='{broken'),completion('good',PLANNER_MODEL,room()))
        provider,_=await self.text(transport)
        self.assertEqual(len(transport.bodies),2)
        a,b=transport.bodies
        self.assertEqual(a['messages'],b['messages'][:2])
        self.assertEqual(a['response_format'],b['response_format'])
        self.assertEqual(provider.diagnostic_for('repair-job')['repair_count'],1)
        self.assertEqual(provider.diagnostic_for('repair-job')['attempts'][0]['validation'],'failed')

    async def test_geometry_fault_uses_exact_product_executor_and_repairs(self):
        bad=room();bad['calls'].append(dict(call_id='bed',tool='place_furniture',
            arguments=dict(id='bed',kind='bed',catalog_version='furniture-blocks-1.0',center_m=[3,3],yaw_deg=0)))
        bad['call_evidence'].append(dict(call_id='bed',basis='user',observation_ids=[],note='Requested bed'))
        transport=ScriptedTransport(completion('bad',PLANNER_MODEL,bad),completion('good',PLANNER_MODEL,room()))
        provider,_=await self.text(transport)
        self.assertIn('floor clearance',provider.diagnostic_for('repair-job')['attempts'][0]['validation_error'])
        self.assertIn('usable_floor_bounds_xy',transport.bodies[1]['messages'][-1]['content'])

    async def test_evidence_repair_reuses_observer_without_invented_refs(self):
        bad=room();bad['call_evidence'][0].update(basis='visual',observation_ids=['invented'])
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,shell_observation()),
            completion('bad',PLANNER_MODEL,bad),completion('fixed',PLANNER_MODEL,room()))
        result=await GenerationService(adapter(transport),config(timeout_s=10),plan_version='2.2').generate(request())
        self.assertEqual(len(transport.bodies),3)
        failure=transport.bodies[-1]['messages'][-1]['content']
        self.assertIn('invented',failure)
        self.assertIn('SOURCE_UNOBSERVED_REFERENCES',failure)
        self.assertEqual([b['model'] for b in transport.bodies],[OBSERVER_MODEL,PLANNER_MODEL,PLANNER_MODEL])
        self.assertEqual(result.image_count,1)

    async def test_observer_truncation_stops_immediately_without_repair(self):
        transport=ScriptedTransport(InvalidProviderResponseError('Chat Completions output was truncated'),
            completion('obs',OBSERVER_MODEL,observation()),completion('bad',PLANNER_MODEL,{'bad':True}))
        with self.assertRaises(InvalidProviderResponseError) as caught:
            await GenerationService(adapter(transport),config(timeout_s=10),plan_version='2.2').generate(request())
        self.assertEqual(len(transport.bodies),1)
        self.assertEqual(caught.exception.diagnostics['repair_count'],0)
        self.assertEqual(caught.exception.code, 'PROVIDER_OUTPUT_TRUNCATED')

    async def test_second_invalid_result_ends_and_preserves_both_failures(self):
        transport=ScriptedTransport(completion('bad',PLANNER_MODEL,{}),completion('again',PLANNER_MODEL,{}))
        with self.assertRaises(InvalidProviderResponseError) as caught:await self.text(transport)
        self.assertEqual(len(transport.bodies),2)
        self.assertEqual([a['validation'] for a in caught.exception.diagnostics['attempts']],['failed','failed'])

    async def test_http_auth_network_timeout_and_identity_are_not_auto_retried(self):
        for error in (ProviderAuthenticationError('unauthorized'),ProviderRequestError('HTTP400'),
                      ProviderTimeoutError('timeout'),completion('wrong','other/model',room())):
            with self.subTest(error=type(error).__name__):
                transport=ScriptedTransport(error)
                with self.assertRaises(Exception):await self.text(transport)
                self.assertEqual(len(transport.bodies),1)

    async def test_remaining_job_deadline_does_not_dispatch_repair(self):
        transport=ScriptedTransport(completion('bad',PLANNER_MODEL,{}))
        with self.assertRaises(InvalidProviderResponseError):
            await GenerationService(adapter(transport),config(timeout_s=1),plan_version='2.2').generate(GenerationRequest('x','Bedroom'))
        self.assertEqual(len(transport.bodies),1)

    async def test_cancelled_late_response_does_not_poison_new_job_diagnostics(self):
        first_started=asyncio.Event();allow_first=asyncio.Event()
        class Transport:
            n=0
            async def complete(self,body,token,conf):
                self.n+=1
                if self.n==1:first_started.set();await allow_first.wait()
                return completion('plan',PLANNER_MODEL,room())
        provider=adapter(Transport());service=GenerationService(provider,config(timeout_s=10),plan_version='2.2')
        old=asyncio.create_task(service.generate(GenerationRequest('old','bedroom')))
        await first_started.wait()
        await service.generate(GenerationRequest('new','bedroom'))
        allow_first.set()
        with self.assertRaises(Exception):await old
        self.assertEqual(provider.diagnostic_for('new')['status'],'validated')


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        self.rates={PLANNER_MODEL:dict(input_per_million='1',output_per_million='1',context_tokens=1000,source='verified:test')}
    def tearDown(self):self.tmp.cleanup()
    def ledger(self):return CampaignLedger(self.root/'campaign.json',approval='test only',rates=self.rates,limit_usd='0.003',max_requests=2)
    def body(self):return dict(model=PLANNER_MODEL,max_tokens=100,response_format={})
    def test_unknown_reservation_survives_restart_and_blocks_budget(self):
        ledger=self.ledger();one=ledger.reserve(self.body());ledger.settle(one)
        reopened=self.ledger();two=reopened.reserve(self.body());reopened.settle(two)
        with self.assertRaises(ProviderConfigurationError):self.ledger().reserve(self.body())
        self.assertEqual(len(self.ledger().state['requests']),2)
    def test_exclusive_inflight_lock_refuses_second_writer(self):
        ledger=self.ledger();one=ledger.reserve(self.body())
        with self.assertRaises(ProviderConfigurationError):self.ledger().reserve(self.body())
        ledger.settle(one)
    def test_explicit_abandonment_refuses_live_owner_and_retains_reservation(self):
        import os
        import subprocess
        import sys
        ledger=self.ledger();one=ledger.reserve(self.body())
        with self.assertRaises(ProviderConfigurationError):
            ledger.acknowledge_abandoned(one,owner_pid=os.getpid(),evidence_ref='test')
        self.assertTrue(ledger.lock_path.exists())
        child=subprocess.Popen([sys.executable,'-c','pass']);child.wait()
        ledger.lock_path.write_text(json.dumps(dict(owner_pid=child.pid,attempt_id=one)))
        ledger.acknowledge_abandoned(one,owner_pid=child.pid,evidence_ref='owned test child exit')
        reopened=self.ledger()
        row=reopened.state['requests'][0]
        self.assertEqual(row['status'],'outcome_unknown')
        self.assertEqual(row['charged_or_reserved_usd'],row['reserved_usd'])
        self.assertEqual(row['billing'],'UNKNOWN')
        self.assertFalse(ledger.lock_path.exists())
    def test_actual_usage_settles_once(self):
        ledger=self.ledger();one=ledger.reserve(self.body())
        ledger.settle(one,usage={'prompt_tokens':10,'completion_tokens':20},status='received')
        ledger.settle(one,usage={'prompt_tokens':0,'completion_tokens':0})
        self.assertEqual(ledger.state['requests'][0]['charged_or_reserved_usd'],'0.00003')
    def test_missing_pricing_prevents_any_dispatch(self):
        body=self.body();body['model']='unverified'
        with self.assertRaises(ProviderConfigurationError):self.ledger().reserve(body)
    def test_verified_observer_addition_preserves_requests_limits_and_old_prices(self):
        ledger=self.ledger();one=ledger.reserve(self.body());ledger.settle(one)
        rate=dict(input_per_million='0.1',output_per_million='0.3',context_tokens=110000,source='https://provider.test/models')
        ledger.register_verified_rate('observer',rate)
        self.assertEqual(len(ledger.state['requests']),1)
        self.assertEqual(ledger.state['max_requests'],2)
        self.assertEqual(ledger.state['limit_usd'],'0.003')
        self.assertEqual(ledger.state['rates'][PLANNER_MODEL],self.rates[PLANNER_MODEL])
        with self.assertRaises(ProviderConfigurationError):ledger.register_verified_rate('observer',{**rate,'output_per_million':'0'})
    def test_secret_image_and_response_body_are_not_public(self):
        secret='secretvalue'
        raw=json.dumps(dict(authorization='Bearer '+secret,api_key=secret,image='data:image/png;base64,YWJj')).encode()
        evidence=InferenceEvidence(self.root/'private');evidence.save('a'*32,{},raw,secret=secret)
        saved=(self.root/'private'/('a'*32+'.json')).read_text()
        self.assertNotIn(secret,saved);self.assertNotIn('YWJj',saved)
        self.assertEqual(_public_generation_diagnostics({'stage':'planner','raw':secret,'attempts':[{'raw':secret,'stage':'observer'}]}),
            {'stage':'planner','attempts':[{'stage':'observer'}], 'attempts_total':1, 'attempts_truncated':False})


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_workers_reject_before_campaign_reservation_or_http(self):
        from twinpulse_provider import UrllibChatCompletionsTransport
        entered=[Event(),Event()];release=Event()
        class Blocked(UrllibChatCompletionsTransport):
            def __init__(self,index):super().__init__(lambda:'not-logged');self.index=index
            def _post(self,*args):
                entered[self.index].set();release.wait(5)
                return completion('plan',PLANNER_MODEL,room())
        tasks=[asyncio.create_task(Blocked(i).complete({},CancellationToken(),config())) for i in range(2)]
        try:
            for ready in entered:self.assertTrue(await asyncio.to_thread(ready.wait,2))
            with TemporaryDirectory() as temp:
                root=Path(temp)
                ledger=CampaignLedger(root/'campaign.json',approval='test',rates={PLANNER_MODEL:dict(
                    input_per_million='1',output_per_million='1',context_tokens=1000,source='test')},limit_usd='.01')
                transport=AuditedChatTransport(lambda:'not-logged',InferenceEvidence(root/'private'),ledger,
                    opener=lambda *a,**k:self.fail('Busy workers must not dispatch'))
                with self.assertRaisesRegex(ProviderRequestError,'no request was dispatched'):
                    await transport.complete(dict(model=PLANNER_MODEL,max_tokens=100,response_format={}),CancellationToken(),config())
                self.assertEqual(ledger.state['requests'],[])
                self.assertFalse(ledger.lock_path.exists())
        finally:
            release.set()
            await asyncio.gather(*tasks)
    async def test_truncated_response_retains_raw_and_billed_usage(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);evidence=InferenceEvidence(root/'private')
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def geturl(self):return config().endpoint_url()
                def read(self,n):return json.dumps({'choices':[{'finish_reason':'length','message':{'content':'partial'}}],
                    'model':PLANNER_MODEL,'id':'returned','usage':{'prompt_tokens':10,'completion_tokens':100}}).encode()
            transport=AuditedChatTransport(lambda:'not-logged',evidence,opener=lambda *a,**k:Response())
            with self.assertRaises(InvalidProviderResponseError):
                await transport.complete(dict(model=PLANNER_MODEL,max_tokens=8000,response_format={}),CancellationToken(),config())
            saved=json.loads(next((root/'private').glob('*.json')).read_text())
            self.assertIn('partial',saved['response_redacted']);self.assertEqual(saved['status'],'rejected')
            self.assertEqual(saved['finish_reason'],'length');self.assertEqual(saved['http_status'],200)
            self.assertEqual(saved['output_pattern'],'incomplete_final_at_limit')
    async def test_cancelled_late_transport_keeps_raw_usage_and_unknown_reservation_until_completion(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);entered=Event();release=Event();token=CancellationToken()
            ledger=CampaignLedger(root/'campaign.json',approval='test',rates={PLANNER_MODEL:dict(
                input_per_million='1',output_per_million='1',context_tokens=1000,source='test')},limit_usd='.01')
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def geturl(self):return config().endpoint_url()
                def read(self,n):
                    entered.set();release.wait(5)
                    return json.dumps(dict(id='response',model=PLANNER_MODEL,choices=[dict(finish_reason='stop',
                        message=dict(content=json.dumps(room())))],usage=dict(prompt_tokens=10,completion_tokens=100))).encode()
            transport=AuditedChatTransport(lambda:'not-logged',InferenceEvidence(root/'private'),ledger,opener=lambda *a,**k:Response())
            task=asyncio.create_task(transport.complete(dict(model=PLANNER_MODEL,max_tokens=100,response_format={}),token,config()))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                token.cancel()
                self.assertEqual(ledger.state['requests'][0]['status'],'outcome_unknown')
                self.assertTrue(ledger.lock_path.exists())
            finally:release.set()
            with self.assertRaises(Exception):await task
            saved=json.loads(next((root/'private').glob('*.json')).read_text())
            self.assertTrue(saved['cancelled']);self.assertIn('bed',saved['response_redacted'])
            self.assertEqual(ledger.state['requests'][0]['usage']['completion_tokens'],100)
            self.assertFalse(ledger.lock_path.exists())


class ProductDeadlineTests(unittest.TestCase):
    # Real authenticated product API + asyncio.run owner, not just wait_for.
    from tests.integration.test_chat_conversation import ChatConversationTests as _Fixture
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    request=_Fixture.request
    product_headers=_Fixture.product_headers
    call=_Fixture.call
    send=_Fixture.send
    answer=_Fixture.answer

    def test_timeout_is_published_before_blocking_worker_finishes_and_late_raw_is_retained(self):
        entered=Event();release=Event()
        with TemporaryDirectory() as temp:
            root=Path(temp)
            ledger=CampaignLedger(root/'campaign.json',approval='test',rates={PLANNER_MODEL:dict(
                input_per_million='1',output_per_million='1',context_tokens=10000,source='test')},limit_usd='.03')
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def geturl(self):return config().endpoint_url()
                def read(self,n):
                    entered.set();release.wait(5)
                    return json.dumps(dict(id='late',model=PLANNER_MODEL,choices=[dict(finish_reason='stop',
                        message=dict(content=json.dumps(room())))],usage=dict(prompt_tokens=10,completion_tokens=100))).encode()
            transport=AuditedChatTransport(lambda:'not-logged',InferenceEvidence(root/'private'),ledger,
                opener=lambda *a,**k:Response())
            gateway=GenerationService(adapter(transport),config(timeout_s=.05),plan_version='2.2')
            self.workflow._application.set_generation_gateway(gateway)
            try:
                initial=self.send();started=time.monotonic();self.call(self.answer(initial))
                deadline=started+1
                while time.monotonic()<deadline:
                    state=self.call()
                    if state['generation']['state']=='failed':break
                    time.sleep(.01)
                self.assertTrue(entered.is_set(),self.workflow.snapshot().get('error'))
                self.assertEqual(state['generation']['state'],'failed')
                self.assertLess(time.monotonic()-started,1)
                self.assertEqual(gateway.diagnostic_snapshot()['status'],'outcome_unknown')
                self.assertEqual(gateway.diagnostic_snapshot()['remote_outcome'],'unknown')
                self.assertTrue(ledger.lock_path.exists())
                self.assertIsNone(self.workflow.snapshot()['site_draft'])
                store=self.workflow._application.diagnostics
                identity=self.workflow.snapshot()['execution_id']
                store.flush();before=store.detail(identity)
                self.assertEqual(before['status'],'failed')
                self.assertEqual(before['first_error']['error_type'],'ProviderTimeoutError')
                self.assertEqual(self.broker.public_state('unowned')['operations'],[])
                with self.assertRaises(ProviderConfigurationError):ledger.reserve(dict(model=PLANNER_MODEL,max_tokens=100,response_format={}))
            finally:
                release.set()
                end=time.monotonic()+3
                while ledger.lock_path.exists() and time.monotonic()<end:time.sleep(.01)
            self.assertFalse(ledger.lock_path.exists())
            saved=json.loads(next((root/'private').glob('*.json')).read_text())
            self.assertTrue(saved['cancelled'])
            self.assertIn('bed',saved['response_redacted'])
            self.assertEqual(ledger.state['requests'][0]['usage']['completion_tokens'],100)
            self.assertEqual(self.call()['generation']['state'],'failed')
            self.assertIsNone(self.workflow.snapshot()['site_draft'])
            store.flush();after=store.detail(identity)
            self.assertEqual(after['status'],'failed')
            self.assertEqual(saved['execution_id'],identity)
            self.assertTrue(any(s['metadata'].get('attempt_id')==saved['attempt_id'] and
                                s['metadata'].get('cancelled') for s in after['spans']))
