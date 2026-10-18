# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline admission and evidence tests; these never contact an API."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_openai_observer import (
    BoundedPhotoLedger,MODEL,ORIGIN,PROMPT,wire_body,AuditedChatTransport,
    InferenceEvidence,ProviderConfig,ProviderCapabilities,CancellationToken,
    ProviderConfigurationError,NebiusChatCompletionsPipelineProvider,GenerationRequest,ImageInput,
)

def original_body():
    builder=NebiusChatCompletionsPipelineProvider(None,observer_model_id=MODEL,
        planner_model_id='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
        site_plan_version='2.2',output_token_cap=10000)
    return builder.build_observer_body(GenerationRequest('offline-test',PROMPT,
        (ImageInput('test.jpg','image/jpeg',b'offline-fixture'),)))

def ledger(root):
    return BoundedPhotoLedger(root/'campaign.json',approval='offline-test-only',rates={MODEL:{
        'input_per_million':'0.75','output_per_million':'4.50','context_tokens':400000,
        'source':'https://developers.openai.com/api/docs/models/gpt-5.4-mini'}},
        limit_usd='0.15',max_requests=2)

class AdmissionTests(unittest.TestCase):
    def test_wire_normalization_preserves_prompt_and_schema_contract(self):
        original=original_body();body=wire_body(original)
        self.assertEqual(original['messages'],body['messages'])
        self.assertEqual(body['max_completion_tokens'],10000)
        self.assertIn('max_tokens',original)
        self.assertNotIn('max_tokens',body)
        self.assertNotIn('temperature',body)
        source=original['response_format']['json_schema']['schema']
        target=body['response_format']['json_schema']['schema']
        self.assertEqual(source['required'],target['required'])
        self.assertEqual(source['properties']['entities']['maxItems'],target['properties']['entities']['maxItems'])
        self.assertEqual(target['properties']['schema_version']['enum'],['1.1'])
        self.assertFalse(target['additionalProperties'])

    def test_bound_tracks_repair_content_and_rejects_other_modalities(self):
        body=wire_body(original_body());first=BoundedPhotoLedger.input_bound(body)
        self.assertGreater(first,40096)
        body['messages'].extend([{'role':'assistant','content':'previous JSON'},
            {'role':'user','content':'repair'}])
        self.assertGreater(BoundedPhotoLedger.input_bound(body),first)
        body['messages'].append({'role':'user','content':'unexpected extra round'})
        with self.assertRaises(ProviderConfigurationError):BoundedPhotoLedger.input_bound(body)
        body=wire_body(original_body());body['messages'][1]['content']=[{'type':'text','text':'no image'}]
        with self.assertRaises(ProviderConfigurationError):BoundedPhotoLedger.input_bound(body)

    def test_two_call_limit_and_inflight_lock_cannot_be_retried(self):
        with TemporaryDirectory() as temp:
            account=ledger(Path(temp));body=wire_body(original_body())
            first=account.reserve(body)
            with self.assertRaises(ProviderConfigurationError):account.reserve(body)
            self.assertTrue(account.lock_path.exists())
            account.settle(first,usage={'prompt_tokens':1000,'completion_tokens':1000},status='received')
            second=account.reserve(body)
            account.settle(second,usage={'prompt_tokens':1000,'completion_tokens':1000},status='received')
            with self.assertRaises(ProviderConfigurationError):account.reserve(body)
            self.assertEqual(len(account.state['requests']),2)
            self.assertFalse(account.lock_path.exists())

    def test_cost_cap_and_wrong_model_fail_before_dispatch(self):
        with TemporaryDirectory() as temp:
            account=ledger(Path(temp));body=wire_body(original_body())
            first=account.reserve(body);account.settle(first,status='outcome_unknown')
            with self.assertRaises(ProviderConfigurationError):account.reserve(body)
            self.assertEqual(len(account.state['requests']),1)
            body['model']='not-approved'
            with self.assertRaises(ProviderConfigurationError):account.reserve(body)
            self.assertFalse(account.lock_path.exists())

class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_modern_output_limit_is_audited_without_credentials_or_input_image(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);body=wire_body(original_body());account=ledger(root)
            config=ProviderConfig(base_url=ORIGIN,endpoint_path='chat/completions',model_id=MODEL,
                api_key_env='UNUSED',capabilities=ProviderCapabilities(True,True,1,('image/jpeg',)),
                timeout_s=120,max_attempts=1)
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def geturl(self):return config.endpoint_url()
                def read(self,n):return json.dumps({'id':'offline-response','model':MODEL,
                    'choices':[{'finish_reason':'stop','message':{'content':'{}'}}],
                    'usage':{'prompt_tokens':1000,'completion_tokens':100}}).encode()
            transport=AuditedChatTransport(lambda:'offline-secret-do-not-log',
                InferenceEvidence(root/'responses'),account,opener=lambda *a,**k:Response())
            result=await transport.complete(body,CancellationToken(),config)
            saved=json.loads((root/'responses'/f'{result.attempt_id}.json').read_text())
            self.assertEqual(saved['max_tokens'],10000)
            self.assertEqual(saved['http_status'],200)
            self.assertEqual(saved['request_sha256'],hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest())
            self.assertNotIn('offline-secret-do-not-log',json.dumps(saved))
            self.assertNotIn('data:image',json.dumps(saved))
            self.assertEqual(account.state['requests'][0]['charged_or_reserved_usd'],'0.0012')
            self.assertFalse(account.lock_path.exists())

if __name__=='__main__':unittest.main()
