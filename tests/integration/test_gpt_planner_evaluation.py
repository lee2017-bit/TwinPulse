# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Scripted routing/accounting regressions; not real model or photo acceptance."""
import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.integration.test_split_provider_evaluation import (
    OBSERVER, PLANNER, REQUEST, OBS, LAYOUT, Transport, account,
    OPENAI_MINI_SNAPSHOT, NANO, ProviderConfigurationError, CancellationToken)
from twinpulse_app.provider_composition import build_split_generation_service
from twinpulse_app.split_evaluation import SplitEvaluationLedger


def composed(plans=None):
    observer=Transport(OBS); planner=Transport(*(plans or [LAYOUT]))
    service=build_split_generation_service(OBSERVER,observer,OBSERVER,planner,
        openai_planner=True,compact_photo_layout=True,output_token_cap=10000,timeout_s=10)
    return service,observer,planner


class GptPlannerTests(unittest.TestCase):
    def test_generic_grounded_schema_has_all_required_fields_and_fits_budget(self):
        import json
        from twinpulse_provider.photo_layout import layout_schema
        from twinpulse_provider.stage_transport import openai_observer_body
        from twinpulse_provider.scene_contract import GROUNDING_REVISION
        observation=dict(schema_version='1.1',summary='Unmeasured room',entities=[dict(
            id='e1',kind='static_obstacle',role='object',category='bed',description='Bed',
            region='middle_right',confidence=.8,spatial_confidence=.7)],
            relations=[],dimensions=[],ambiguities=['Unknown scale'])
        from twinpulse_provider.nebius_pipeline import ObservationArtifact
        schema=layout_schema(REQUEST.prompt,observation=ObservationArtifact.from_mapping(observation),revision=GROUNDING_REVISION)
        body=openai_observer_body(dict(model=OPENAI_MINI_SNAPSHOT,max_tokens=10000,
            messages=[dict(role='user',content=json.dumps(observation))],response_format=dict(
                type='json_schema',json_schema=dict(name='twinpulse_compact_photo_layout',strict=True,schema=schema))))
        def walk(node):
            if isinstance(node,dict):
                if node.get('type')=='object':
                    self.assertEqual(set(node.get('properties',{})),set(node.get('required',[])))
                    self.assertIs(node.get('additionalProperties'),False)
                for value in node.values():walk(value)
            elif isinstance(node,list):
                for value in node:walk(value)
        walk(body['response_format']['json_schema']['schema'])
        self.assertEqual(body['response_format']['json_schema']['schema']['properties']['objects']['items']['properties']['yaw_deg']['type'],'integer')
        self.assertLess(SplitEvaluationLedger.text_input_bound(body)*.75/1000000+.045,.15)

    def test_numeric_constants_and_nullable_enums_keep_their_types(self):
        from twinpulse_provider.stage_transport import openai_observer_body
        schema=dict(type='object',properties=dict(size={'type':'number','const':4.5},
            flag={'enum':[True,False]},nullable={'enum':['floor',None]}))
        original=dict(max_tokens=10000,messages=[],response_format=dict(json_schema=dict(schema=schema)))
        result=openai_observer_body(original)['response_format']['json_schema']['schema']['properties']
        self.assertEqual(result['size'],{'type':'number','enum':[4.5]})
        self.assertEqual(result['flag']['type'],'boolean')
        self.assertEqual(result['nullable']['type'],['string','null'])
        self.assertIn('const',schema['properties']['size'])

    def test_both_stages_use_gpt_but_are_distinct_and_planner_has_no_image(self):
        service,observer,planner=composed()
        asyncio.run(service.generate(REQUEST))
        for transport in (observer,planner):
            body,config=transport.calls[0]
            self.assertEqual(config.model_id,OPENAI_MINI_SNAPSHOT)
            self.assertEqual(config.base_url,'https://api.openai.com/v1/')
            self.assertEqual(body['max_completion_tokens'],10000)
            self.assertEqual(body['reasoning_effort'],'low')
            self.assertNotIn('max_tokens',body)
            self.assertNotIn('temperature',body)
            self.assertNotIn('chat_template_kwargs',body)
        self.assertNotIn('data:image',str(planner.calls[0][0]))
        self.assertIn('being mentioned by the user does not replace coverage',planner.calls[0][0]['messages'][0]['content'])
        self.assertNotEqual(observer.calls[0][0]['response_format']['json_schema']['name'],
                            planner.calls[0][0]['response_format']['json_schema']['name'])

    def test_single_validation_repair_is_gpt_and_shared(self):
        service,observer,planner=composed([{},LAYOUT])
        asyncio.run(service.generate(REQUEST))
        self.assertEqual((len(observer.calls),len(planner.calls)),(1,2))
        self.assertEqual(service._provider.diagnostic_for(REQUEST.request_id)['repair_count'],1)
        self.assertEqual(len(planner.calls[1][0]['messages']),4)

    def test_default_mixed_composition_does_not_authorize_gpt_planner(self):
        with self.assertRaises(ProviderConfigurationError):
            build_split_generation_service(OBSERVER,Transport(),OBSERVER,Transport())
        for kwargs,settings in (({'openai_planner':True},PLANNER),
                ({'openai_planner':True,'planner_template_no_thinking':True},OBSERVER)):
            with self.assertRaises(ProviderConfigurationError):
                build_split_generation_service(OBSERVER,Transport(),settings,Transport(),**kwargs)

    def test_unknown_stage_and_planner_image_leak_block_before_http(self):
        service,observer,planner=composed()
        body=service._provider.build_observer_body(REQUEST)
        body['response_format']['json_schema']['name']='twinpulse_compact_photo_layout'
        with self.assertRaises(ProviderConfigurationError):
            asyncio.run(service._provider._transport.complete(body,CancellationToken(),service._config))
        body['response_format']['json_schema']['name']='unknown'
        with self.assertRaises(ProviderConfigurationError):
            asyncio.run(service._provider._transport.complete(body,CancellationToken(),service._config))
        self.assertFalse(observer.calls or planner.calls)

    def test_same_model_two_stage_accounting_and_shared_per_run_cap(self):
        service,observer,planner=composed()
        asyncio.run(service.generate(REQUEST))
        with TemporaryDirectory() as temp:
            original=account(Path(temp))
            ledger=SplitEvaluationLedger(original.path,approval='offline-only',rates=original.state['rates'],
                max_requests=10,limit_usd='.15',openai_planner=True,run_request_cap=2)
            for transport in (observer,planner):
                identity=ledger.reserve(transport.calls[0][0])
                ledger.settle(identity,usage={'prompt_tokens':1000,'completion_tokens':100},status='received')
            self.assertEqual(len(ledger.state['requests']),2)
            self.assertNotEqual(ledger.state['requests'][0]['stage_schema'],ledger.state['requests'][1]['stage_schema'])
            with self.assertRaises(ProviderConfigurationError):ledger.reserve(planner.calls[0][0])
            self.assertFalse(ledger.lock_path.exists())

    def test_mixed_ledger_cannot_authorize_gpt_planner_and_gpt_cannot_authorize_nano(self):
        service,_,planner=composed();asyncio.run(service.generate(REQUEST))
        with TemporaryDirectory() as temp:
            ledger=account(Path(temp))
            with self.assertRaises(ProviderConfigurationError):ledger.reserve(planner.calls[0][0])
            ledger.openai_planner=True
            with self.assertRaises(ProviderConfigurationError):ledger.reserve({'model':NANO,'max_tokens':10000})
            self.assertFalse(ledger.state['requests'])
            self.assertFalse(ledger.lock_path.exists())

    def test_continued_parent_ledger_cannot_dispatch_again(self):
        with TemporaryDirectory() as temp:
            ledger=account(Path(temp))
            with ledger.path.with_suffix('.continued-to').open('x',encoding='utf-8') as stream:
                stream.write('{}')
            with self.assertRaises(ProviderConfigurationError):ledger.reserve({'model':NANO,'max_tokens':10000})
            self.assertFalse(ledger.state['requests'])
            self.assertFalse(ledger.lock_path.exists())

    def test_text_bound_covers_full_schema_and_repair_without_mutation(self):
        service,_,planner=composed([{},LAYOUT]);asyncio.run(service.generate(REQUEST))
        body=planner.calls[1][0];before=deepcopy(body)
        import json
        self.assertEqual(SplitEvaluationLedger.text_input_bound(body),
            len(json.dumps(body,ensure_ascii=False).encode('utf-8'))+4096)
        self.assertEqual(body,before)
        body['messages'].append({'role':'user','content':'extra'})
        with self.assertRaises(ProviderConfigurationError):SplitEvaluationLedger.text_input_bound(body)

if __name__=='__main__':unittest.main()
