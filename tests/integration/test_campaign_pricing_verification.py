# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Existing approval extension/prices survive catalogue verification; no network."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import subprocess
import sys
from unittest.mock import patch

from twinpulse_core.revisions import canonical_sha256
from twinpulse_provider.reliability import CampaignLedger
from scripts import verify_agent_reliability as verifier

class PricingVerificationTests(unittest.TestCase):
    def check(self,changed=False):
        with TemporaryDirectory() as temp:
            root=Path(temp);path=root/'campaign.json'
            rates={model:dict(input_per_million='0.1',output_per_million='0.3',
                context_tokens=1000,source='https://existing.test',verified_at='original')
                for model in ('observer','planner')}
            ledger=CampaignLedger(path,approval='synthetic test only',rates=rates)
            ledger.state.update(max_requests=160,additional_batch_approvals=[dict(
                batch_id='test-extension',approval='synthetic test only',approved_at='test',
                start_count=0,new_batch_cap=100,carry_forward_remaining=60,
                old_max_requests=60,new_max_requests=160,unchanged_limit_usd='1.00',
                prior_requests_sha256=canonical_sha256([]))])
            ledger._write();before=path.read_bytes()
            rows=[dict(flavors=[dict(model_id=model,use_cases=['image'],
                input_price_per_million_tokens=.1,output_price_per_million_tokens=.4 if changed else .3,
                max_model_len=1000)]) for model in rates]
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,n):return json.dumps(rows).encode()
            settings=SimpleNamespace(observer_model_id='observer',model_id='planner',credential_ref='test')
            settings.validated=lambda:settings
            args=SimpleNamespace(live=True,output=root/'output',campaign=path,
                inspect_abandoned_owned_run=None,verify_pricing_only=True)
            with patch.object(verifier,'JsonProviderSettingsStore') as config, \
                    patch.object(verifier,'WindowsCredentialStore') as credentials, \
                    patch.object(verifier.urllib.request,'build_opener') as opener:
                config.return_value.load.return_value=settings
                credentials.return_value.load.return_value='test-not-a-secret'
                opener.return_value.open.return_value=Response()
                if changed:
                    with self.assertRaisesRegex(SystemExit,'pricing differs'):asyncio.run(verifier.run(args))
                    self.assertFalse((root/'output/pricing.json').exists())
                else:
                    self.assertEqual(asyncio.run(verifier.run(args)),0)
                    evidence=json.loads((root/'output/pricing.json').read_text())
                    self.assertEqual(evidence['inference_requests'],0)
                    self.assertEqual(len(evidence['models']),2)
                self.assertEqual(opener.return_value.open.call_count,1)
            self.assertEqual(path.read_bytes(),before)
    def test_extended_approval_and_original_rates_are_not_reset(self):self.check()
    def test_price_change_blocks_without_rewriting_campaign(self):self.check(True)
    def test_journey_cap_rejects_over_five_or_nonlive_override_before_launch(self):
        script=Path(verifier.ROOT)/'scripts/verify_chat_sim_journey.py'
        for flags,reason in ((['--live-request-cap','6'],'invalid choice'),
                             (['--live-request-cap','1'],'requires an explicit approved campaign')):
            with self.subTest(flags=flags):
                result=subprocess.run([sys.executable,'-B',str(script),'unused-not-created','--case','text',*flags],
                    capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(reason,result.stderr)
