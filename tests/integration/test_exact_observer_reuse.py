# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline provenance checks; synthetic test evidence is not live acceptance."""
import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from scripts.verify_agent_reliability import ReuseExactAuditedObserver
from packages.twinpulse_provider.tests.test_nebius_pipeline import (
    ScriptedTransport,completion,config,request,observation,OBSERVER_MODEL,PLANNER_MODEL)
from twinpulse_provider import CancellationToken,GenerationRequest,ImageInput,NebiusChatCompletionsPipelineProvider
from twinpulse_provider.reliability import InferenceEvidence


class ExactObserverReuseTests(unittest.TestCase):
    def setup_evidence(self,root,*,status='received',finished=True,site_version='2.2'):
        self.identity='1'*32
        adapter=NebiusChatCompletionsPipelineProvider(ScriptedTransport(),observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version=site_version)
        self.body=adapter.build_observer_body(request())
        payload=dict(id='fixture-only',model=OBSERVER_MODEL,choices=[dict(finish_reason='stop',
            message=dict(content=json.dumps(observation())))],usage=dict(prompt_tokens=10,completion_tokens=20))
        InferenceEvidence(root).save(self.identity,dict(attempt_id=self.identity,model_id=OBSERVER_MODEL,
            status=status,http_status=200,request_sha256=hashlib.sha256(json.dumps(self.body,sort_keys=True).encode()).hexdigest(),
            schema_sha256=hashlib.sha256(json.dumps(self.body['response_format'],sort_keys=True).encode()).hexdigest()),
            json.dumps(payload).encode())
        return SimpleNamespace(state=dict(requests=[dict(attempt_id=self.identity,status=status,
            model_id=OBSERVER_MODEL,finished_at='fixture timestamp' if finished else None)]))

    def test_exact_reuse_once_then_delegate_planner_only(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);ledger=self.setup_evidence(root)
            transport=ScriptedTransport(completion('planner',PLANNER_MODEL,{}))
            reuse=ReuseExactAuditedObserver(transport,ledger,root,self.identity)
            actual=asyncio.run(reuse.complete(self.body,CancellationToken(),config()))
            self.assertEqual(actual.attempt_id,self.identity)
            self.assertEqual(len(transport.bodies),0)
            asyncio.run(reuse.complete(dict(model=PLANNER_MODEL),CancellationToken(),config()))
            self.assertEqual(len(transport.bodies),1)

    def test_current_wire12_exact_reuse_is_supported_but_host_derived13_is_not(self):
        from twinpulse_provider.nebius_pipeline import observation_json_schema
        with TemporaryDirectory() as directory:
            root=Path(directory);ledger=self.setup_evidence(root)
            self.assertEqual(self.body['response_format']['json_schema']['schema'],observation_json_schema('1.2'))
            transport=ScriptedTransport()
            reuse=ReuseExactAuditedObserver(transport,ledger,root,self.identity)
            actual=asyncio.run(reuse.complete(self.body,CancellationToken(),config()))
            self.assertEqual(actual.attempt_id,self.identity)
            self.assertEqual(transport.bodies,[])
        # The host-only expansion is not a provider wire schema.
        with self.assertRaises(ValueError):observation_json_schema('1.3')

    def test_changed_photo_prompt_model_schema_rejected_before_delegate(self):
        for field,value in (('messages',[]),('model',PLANNER_MODEL),('response_format',{}),('max_tokens',10000)):
            with TemporaryDirectory() as directory:
                root=Path(directory);ledger=self.setup_evidence(root);transport=ScriptedTransport()
                reuse=ReuseExactAuditedObserver(transport,ledger,root,self.identity)
                changed={**self.body,field:value}
                with self.assertRaisesRegex(ValueError,'does not match'):
                    asyncio.run(reuse.complete(changed,CancellationToken(),config()))
                self.assertEqual(transport.bodies,[])
                self.assertFalse(reuse.used)

    def test_legacy_schema10_exact_reuse_remains_supported(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);ledger=self.setup_evidence(root,site_version='2.1')
            transport=ScriptedTransport()
            reuse=ReuseExactAuditedObserver(transport,ledger,root,self.identity)
            actual=asyncio.run(reuse.complete(self.body,CancellationToken(),config()))
            self.assertEqual(actual.attempt_id,self.identity)
            self.assertTrue(reuse.used)
            self.assertEqual(transport.bodies,[])

    def test_tampered_response_and_incomplete_ledger_rejected(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);ledger=self.setup_evidence(root)
            path=root/(self.identity+'.json');value=json.loads(path.read_text())
            value['response_redacted']+=' '
            # Fixture corruption only; production evidence is never rewritten.
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                ReuseExactAuditedObserver(ScriptedTransport(),ledger,root,self.identity)
        for status,finished in (('outcome_unknown',False),('received',False),('rejected',True)):
            with TemporaryDirectory() as directory:
                root=Path(directory);ledger=self.setup_evidence(root,status=status,finished=finished)
                with self.assertRaisesRegex(ValueError,'completed successful'):
                    ReuseExactAuditedObserver(ScriptedTransport(),ledger,root,self.identity)

    def test_unsafe_attempt_path_and_cancelled_reuse_rejected(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);ledger=self.setup_evidence(root)
            with self.assertRaises(ValueError):
                ReuseExactAuditedObserver(ScriptedTransport(),ledger,root,'../other')
            reuse=ReuseExactAuditedObserver(ScriptedTransport(),ledger,root,self.identity)
            token=CancellationToken();token.cancel()
            with self.assertRaisesRegex(ValueError,'Cancelled'):
                asyncio.run(reuse.complete(self.body,token,config()))
