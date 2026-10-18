# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Zero-network deadline/late-usage tests; synthetic delays are not model scores."""
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.benchmark_late_usage import CollectingLedger,LateUsageCollector
from scripts.compare_model_roles_live import role_attempt_snapshot,role_terminal_stop,run_case
from twinpulse_provider.contracts import CancellationToken,ProviderConfig,ProviderCapabilities
from twinpulse_provider.errors import ProviderConfigurationError,ProviderTimeoutError
from twinpulse_provider.reliability import AuditedChatTransport,InferenceEvidence,CampaignLedger
from twinpulse_provider.generation_policy import ExecutionBudget
from twinpulse_provider.nebius_pipeline import ObservationArtifact

RATES={name:dict(input_per_million='1',output_per_million='2',context_tokens=1000,
    source='https://example.invalid/frozen-prices') for name in ('slow','fast')}
BODY=lambda name:dict(model=name,max_tokens=100,response_format=dict(type='json_schema',
    json_schema=dict(name='fixture',schema=dict(type='object'))),messages=[])

class Response:
    status=200
    def __init__(self,url,release=None,finish='stop',usage=True):
        self.url=url;self.release=release;self.finish=finish;self.usage=usage
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def geturl(self):return self.url
    def read(self,*_):
        if self.release and not self.release.wait(2):raise TimeoutError('offline fixture exceeded bound')
        payload=dict(id='offline-response',model='fixture',choices=[dict(finish_reason=self.finish,message=dict(content='{}'))])
        if self.usage:payload['usage']=dict(prompt_tokens=10,completion_tokens=5,total_tokens=15)
        return json.dumps(payload).encode()

class LateUsageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.collector=LateUsageCollector(self.root/'collection',expires_at='2099-01-01T00:00:00+00:00',receive_timeout_s=.5)
        self.ledger=CollectingLedger(self.root/'ledger.json',approval='offline explicit fixture',rates=RATES,limit_usd='.01',max_requests=20)
        self.release=Event();self.calls=[]
    async def asyncTearDown(self):
        self.release.set();await self.collector.drain();self.ledger.close();self.temp.cleanup()
    def config(self,model,timeout=.02):
        return ProviderConfig('https://example.invalid/v1/','chat/completions',model,'UNUSED',ProviderCapabilities(True,True,1),timeout_s=timeout)
    def transport(self,name,*,finish='stop',usage=True,error=None):
        evidence=InferenceEvidence(self.root/name)
        def opener(request,**kwargs):
            self.calls.append((json.loads(request.data)['model'],kwargs['timeout']))
            if error:
                self.release.wait(2);raise error
            return Response(request.full_url,self.release if name=='slow' else None,finish,usage)
        return AuditedChatTransport(lambda:'offline-not-a-real-key',evidence,self.ledger,opener=opener,collection=self.collector)
    async def test_timeout_is_fail_next_model_runs_and_same_response_settles(self):
        slow=self.transport('slow');token=CancellationToken()
        with self.assertRaises(ProviderTimeoutError):
            await slow.complete(BODY('slow'),token,self.config('slow'))
        attempt=slow.calls[0];snapshot=dict(status='FAIL',failure_code='PROVIDER_TIMEOUT')
        attempts,errors=role_attempt_snapshot(slow.calls,slow.evidence.root,self.ledger)
        self.assertIsNone(role_terminal_stop(snapshot,attempts,errors,self.ledger))
        self.assertEqual(attempts[0]['estimated_or_reserved_usd'],'0.0012')
        self.assertEqual(self.collector.snapshot()['active_receivers'],1)
        fast=self.transport('fast')
        result=await fast.complete(BODY('fast'),CancellationToken(),self.config('fast',.2))
        self.assertEqual(result.finish_reason,'stop')
        self.assertFalse(self.release.is_set())  # next model completed BEFORE old response
        self.release.set();await self.collector.drain()
        row=next(r for r in self.ledger.state['requests'] if r['attempt_id']==attempt)
        self.assertEqual(row['usage']['completion_tokens'],5)
        self.assertEqual(row['charged_or_reserved_usd'],'0.00002')
        self.assertEqual(snapshot['status'],'FAIL')
        receipt=json.loads((self.root/'collection/settlements'/f'{attempt}.json').read_text(encoding='utf-8'))
        self.assertTrue(receipt['trial_timed_out']);self.assertFalse(receipt['trial_result_rewritten'])
        self.assertEqual(len(self.calls),2)  # no retransmission of timed-out call
        self.assertEqual(self.calls[0][1],.5)
        raw=(slow.evidence.root/f'{attempt}.json').read_text(encoding='utf-8')
        self.assertNotIn('offline-not-a-real-key',raw)

    async def test_lost_response_retains_hold_not_zero(self):
        slow=self.transport('slow',error=TimeoutError('offline lost response'))
        with self.assertRaises(ProviderTimeoutError):await slow.complete(BODY('slow'),CancellationToken(),self.config('slow'))
        self.release.set();await self.collector.drain()
        row=self.ledger.state['requests'][0]
        self.assertEqual(row['status'],'outcome_unknown');self.assertNotIn('usage',row)
        self.assertEqual(row['charged_or_reserved_usd'],'0.0012')

    async def test_late_output_limit_stops_subsequent_paid_dispatch(self):
        slow=self.transport('slow',finish='length')
        with self.assertRaises(ProviderTimeoutError):await slow.complete(BODY('slow'),CancellationToken(),self.config('slow'))
        self.release.set();await self.collector.drain()
        self.assertEqual(self.collector.stop_reason(),'OUTPUT_LIMIT')
        before=len(self.calls)
        with self.assertRaises(ProviderConfigurationError):await self.transport('fast').complete(BODY('fast'),CancellationToken(),self.config('fast'))
        self.assertEqual(len(self.calls),before)

    async def test_missing_usage_keeps_reserve_even_if_raw_received(self):
        slow=self.transport('slow',usage=False)
        with self.assertRaises(ProviderTimeoutError):await slow.complete(BODY('slow'),CancellationToken(),self.config('slow'))
        self.release.set();await self.collector.drain()
        self.assertEqual(self.ledger.state['requests'][0]['charged_or_reserved_usd'],'0.0012')
        attempts,errors=role_attempt_snapshot(slow.calls,slow.evidence.root,self.ledger)
        self.assertIsNone(role_terminal_stop(dict(failure_code='PROVIDER_TIMEOUT'),attempts,errors,self.ledger))
        self.ledger.timeout_ids.clear()
        self.assertEqual(role_terminal_stop(dict(failure_code='PROVIDER_TIMEOUT'),attempts,errors,self.ledger),'REMOTE_UNKNOWN')

    async def test_remaining_money_includes_pending_reservation(self):
        slow=self.transport('slow')
        with self.assertRaises(ProviderTimeoutError):await slow.complete(BODY('slow'),CancellationToken(),self.config('slow'))
        # Reserve worst case, not the unknown actual. No refund while waiting.
        self.ledger.state['limit_usd']='.0013';self.ledger._write()
        with self.assertRaisesRegex(ProviderConfigurationError,'budget'):
            self.ledger.reserve(BODY('fast'))
        self.assertEqual(len(self.ledger.state['requests']),1)

    async def test_unacknowledged_unknown_and_unreadable_settled_raw_still_stop(self):
        identity=self.ledger.reserve(BODY('slow'))
        attempts,errors=role_attempt_snapshot([identity],self.root/'absent',self.ledger)
        self.assertEqual(role_terminal_stop(dict(failure_code='PROVIDER_TIMEOUT'),attempts,errors,self.ledger),'REMOTE_UNKNOWN')
        self.ledger.settle(identity,status='outcome_unknown')

    async def test_expired_authority_sends_nothing(self):
        self.collector.expiry=datetime.now(timezone.utc)-timedelta(seconds=1)
        with self.assertRaisesRegex(ProviderConfigurationError,'EXPIRED'):
            await self.transport('fast').complete(BODY('fast'),CancellationToken(),self.config('fast'))
        self.assertEqual(self.calls,[]);self.assertEqual(self.ledger.state['requests'],[])

    async def test_real_role_pipeline_enclosing_deadline_keeps_receiver_and_next_model(self):
        photo=self.root/'fixture.jpg';photo.write_bytes(b'offline-image-fixture')
        observed=ObservationArtifact.from_mapping(dict(schema_version='1.0',summary='Offline fixture',
            entities=[],relations=[],dimensions=[],ambiguities=['Unmeasured']))
        def opener(request,**kwargs):
            self.calls.append(('slow',kwargs['timeout']))
            return Response(request.full_url,self.release)
        with patch('urllib.request.build_opener',return_value=SimpleNamespace(open=opener)), \
                patch.object(ExecutionBudget,'timeout_for',return_value=.02):
            row=await run_case(self.root/'product','planner',dict(provider='nebius',model_id='slow'),1,
                {'nebius':SimpleNamespace(load=lambda:'offline-not-a-real-key')},self.ledger,observed,
                dict(photo_sha256=hashlib.sha256(photo.read_bytes()).hexdigest(),observation_sha256='offline'),
                photo=photo,prompt='Offline room fixture',output_cap=100,
                expires_at='2099-01-01T00:00:00+00:00',collection=self.collector)
        self.assertEqual((row['status'],row['failure_code'],row['actual_calls']),('FAIL','PROVIDER_TIMEOUT',1))
        self.assertIsNone(row['terminal_stop'])
        self.assertEqual(self.collector.snapshot()['active_receivers'],1)
        identity=row['attempt_ids'][0]
        receipt=json.loads((self.root/'collection/timeouts'/f'{identity}.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['deadline_origin'],'budgeted_pipeline_per_call')
        self.assertEqual(receipt['scored_timeout_s'],.02)
        self.collector.record_enclosing_deadline([],self.ledger,scored_timeout_s=.02)
        await self.transport('fast').complete(BODY('fast'),CancellationToken(),self.config('fast',.2))
        self.assertFalse(self.release.is_set())
        self.release.set();await self.collector.drain()
        self.assertEqual(self.ledger.state['requests'][0]['charged_or_reserved_usd'],'0.00002')
        self.assertEqual(row['status'],'FAIL');self.assertEqual(len(self.calls),2)

    async def test_arbitrary_cancellation_does_not_become_scored_timeout(self):
        slow=self.transport('slow')
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(slow.complete(BODY('slow'),CancellationToken(),self.config('slow',.2)),.01)
        self.assertEqual(self.collector.snapshot()['active_receivers'],1)
        self.assertEqual(self.ledger.timeout_ids,set())
        attempts,errors=role_attempt_snapshot(slow.calls,slow.evidence.root,self.ledger)
        self.assertEqual(role_terminal_stop(dict(failure_code='PROVIDER_TIMEOUT'),attempts,errors,self.ledger),'REMOTE_UNKNOWN')
        self.assertEqual(list((self.root/'collection/timeouts').glob('*.json')),[])

class LedgerSafetyTests(unittest.TestCase):
    def test_no_duplicate_settlement_no_adoption_no_foreign_lock_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=CollectingLedger(root/'ledger.json',approval='fixture',rates=RATES,limit_usd='.01')
            a=ledger.reserve(BODY('slow'));b=ledger.reserve(BODY('fast'))
            ledger.settle(b,usage=dict(prompt_tokens=10,completion_tokens=5),status='received')
            ledger.settle(a,usage=dict(prompt_tokens=10,completion_tokens=5),status='received')
            prior=json.dumps(ledger.state,sort_keys=True)
            ledger.settle(a,usage=dict(prompt_tokens=0,completion_tokens=0),status='received')
            self.assertEqual(prior,json.dumps(ledger.state,sort_keys=True))
            with self.assertRaisesRegex(ProviderConfigurationError,'NEW_LEDGER'):
                CollectingLedger(root/'ledger.json',approval='fixture',rates=RATES,limit_usd='.01')
            ledger.lock_path.write_text('foreign',encoding='utf-8')
            with self.assertRaises(FileExistsError):ledger.reserve(BODY('fast'))
            self.assertEqual(ledger.lock_path.read_text(encoding='utf-8'),'foreign')
            ledger.lock_path.unlink()  # only this fixture-created lock
            ledger.close()

    def test_product_default_still_single_dispatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=CampaignLedger(Path(folder)/'product.json',approval='fixture',rates=RATES,limit_usd='.01')
            first=ledger.reserve(BODY('slow'))
            with self.assertRaisesRegex(ProviderConfigurationError,'in-flight'):ledger.reserve(BODY('fast'))
            ledger.settle(first,status='outcome_unknown')

if __name__=='__main__':unittest.main()
