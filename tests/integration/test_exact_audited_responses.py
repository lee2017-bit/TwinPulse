# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic evidence checks only; not real model or Isaac acceptance."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.replay_audited_inference import ExactAuditedResponses, live_run_inputs, failed_packing_run_inputs, expected_failed_packing_plan
from tests.integration.test_exact_observer_reuse import ExactObserverReuseTests
from twinpulse_provider import CancellationToken
from packages.twinpulse_provider.tests.test_nebius_pipeline import config


class AuditedResponsesTests(unittest.TestCase):
    def test_failed_packing_replay_is_explicit_and_does_not_invent_accepted_plan(self):
        root=Path(__file__).resolve().parents[2]/'artifacts/pre-demo-20261008/photo-semantic-add10-r4'
        if not (root/'result.json').is_file():self.skipTest('Original real rejected run is not in portable test package')
        original=(root/'result.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'contract unavailable'):live_run_inputs(root)
        source,evidence,ids=failed_packing_run_inputs(root)
        self.assertIsNone(source.plan_sha256);self.assertIsNone(source.site)
        self.assertEqual(len(ids),2)
        record=__import__('twinpulse_app.project_store',fromlist=['ProjectStore']).ProjectStore(root/'runtime/active_project.json').load()
        self.assertEqual(source.input_revision.digest,record.latest_input.digest)
        photo=root.parents[1]/'agent-reliability-20261007/photo-output10000-chat-isaac-r1/1-사진-1.jpg'
        # Never invoke a transport or credential store to derive the new expected
        # plan from the old rejection. Historical source has no accepted hash.
        with patch('scripts.replay_audited_inference.ExactAuditedResponses.complete',side_effect=AssertionError('No transport in compile')):
            plan,provenance,quality=expected_failed_packing_plan(source,evidence,ids,photo)
        self.assertEqual(provenance['compiler_revision'],'photo-layout-compiler-1.7')
        self.assertEqual(quality['room_estimate_m'],[3.5,4.])
        self.assertEqual(quality['issues'],[]);self.assertEqual(len(quality['checks']),32)
        self.assertIsNone(source.plan_sha256)
        for change in ('status','closed','code','validation','attempt'):
            bad=json.loads(original)
            if change=='status':bad['status']='PASS'
            elif change=='closed':bad['browser']['browser_closed']=False
            else:
                progress=bad['browser']['workflow']['generation_progress']
                if change=='code':progress['validation_code']='PHOTO_SCALE_REVIEW_REQUIRED'
                elif change=='validation':progress['attempts'][1]['validation']='passed'
                else:progress['attempts'][0]['attempt_id']='0'*32
            with self.subTest(change=change),patch('scripts.replay_audited_inference.json.loads',side_effect=[bad,*[json.loads(p.read_text(encoding='utf-8')) for p in evidence.glob('*.json')]]),patch('twinpulse_app.project_store.ProjectStore') as store:
                store.return_value.load.return_value=record
                with self.assertRaisesRegex(ValueError,'exact stopped'):failed_packing_run_inputs(root)
        self.assertEqual((root/'result.json').read_bytes(),original)

    def test_three_response_replay_requires_exact_accepted_repair_history(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);evidence=root/'runtime/provider-evidence';evidence.mkdir(parents=True)
            ids=[format(i,'032x') for i in (1,2,3)]
            for n,identity in enumerate(ids):
                (evidence/(identity+'.json')).write_text(json.dumps(dict(
                    attempt_id=identity,started_at=str(n))),encoding='utf-8')
            report=dict(provider='live_configured_provider',photo_inference='LIVE',
                experimental_compact_photo=True,supervisor={'phase':'stopped'},status='FAIL')
            source=root/'result.json';source.write_text(json.dumps(report),encoding='utf-8');before=source.read_bytes()
            draft=SimpleNamespace(input_revision=SimpleNamespace(
                generation_settings={'request_schema':'photo-layout-1.1'},images=[{'sha256':'a'*64}]),
                plan=SimpleNamespace(to_dict=lambda:{}))
            valid=dict(repair_count=1,attempts=[dict(attempt_id=i,stage=s,validation=v) for i,s,v in zip(
                ids,['observer','planner','planner'],['passed','failed','passed'])])
            with patch('twinpulse_app.project_store.ProjectStore') as store, \
                 patch('twinpulse_core.photo_quality.inspect_photo_geometry',return_value={}), \
                 patch('scripts.summarize_live_photo_product.checked_generation_progress',return_value=valid) as checked:
                store.return_value.load.return_value=SimpleNamespace(site_draft=draft)
                self.assertEqual(live_run_inputs(root),(draft,evidence,ids))
                for change in ('count','identity','stage','validation'):
                    broken=json.loads(json.dumps(valid))
                    if change=='count':broken['repair_count']=0
                    elif change=='identity':broken['attempts'][1]['attempt_id']=ids[2]
                    elif change=='stage':broken['attempts'][2]['stage']='observer'
                    else:broken['attempts'][2]['validation']='failed'
                    checked.return_value=broken
                    with self.subTest(change=change),self.assertRaisesRegex(ValueError,'original accepted plan'):
                        live_run_inputs(root)
            self.assertEqual(source.read_bytes(),before)

    def prepare(self, root):
        fixture=ExactObserverReuseTests()
        ledger=fixture.setup_evidence(root)
        campaign=root/'campaign.json'
        campaign.write_text(json.dumps(ledger.state),encoding='utf-8')
        return fixture, campaign

    def test_exact_one_use_without_fallback_or_ledger_write(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);fixture,campaign=self.prepare(root)
            before=campaign.read_bytes()
            replay=ExactAuditedResponses(campaign,root,[fixture.identity])
            response=asyncio.run(replay.complete(fixture.body,CancellationToken(),config()))
            self.assertEqual(response.attempt_id,fixture.identity)
            with self.assertRaisesRegex(ValueError,'exhausted'):
                asyncio.run(replay.complete(fixture.body,CancellationToken(),config()))
            self.assertEqual(campaign.read_bytes(),before)

    def test_changed_request_does_not_consume_response(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);fixture,campaign=self.prepare(root)
            replay=ExactAuditedResponses(campaign,root,[fixture.identity])
            with self.assertRaisesRegex(ValueError,'exact original'):
                asyncio.run(replay.complete({**fixture.body,'messages':[]},CancellationToken(),config()))
            self.assertEqual(replay.used,0)

    def test_tampered_incomplete_or_unsafe_evidence_rejected(self):
        for change in ('raw','ledger','truncated','path','duplicate'):
            with self.subTest(change=change),TemporaryDirectory() as directory:
                root=Path(directory);fixture,campaign=self.prepare(root)
                path=root/(fixture.identity+'.json');item=json.loads(path.read_text())
                ids=[fixture.identity]
                if change=='raw':item['response_redacted']+=' '
                if change=='truncated':item['response_truncated']=True
                if change=='ledger':campaign.write_text(json.dumps({'requests':[]}),encoding='utf-8')
                if change=='path':ids=['../other']
                if change=='duplicate':ids*=2
                path.write_text(json.dumps(item),encoding='utf-8')
                with self.assertRaises(ValueError):ExactAuditedResponses(campaign,root,ids)
