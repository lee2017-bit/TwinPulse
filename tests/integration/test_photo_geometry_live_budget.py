# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local evaluation guards only. No credentials, HTTP or robot operations."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.verify_photo_geometry_live import extend_approved_batch, LimitedTransport, remaining_approved_allowance
from twinpulse_provider.reliability import CampaignLedger
from twinpulse_provider import ProviderConfigurationError


class PhotoGeometryLiveBudgetTests(unittest.TestCase):
    def test_natural_only_preflight_never_compiles_unrelated_old_negative(self):
        from scripts.verify_photo_geometry_live import controlled_negative_preflight
        with patch('scripts.verify_photo_geometry_live.compile_layout',side_effect=ValueError('obsolete negative')) as compile:
            self.assertEqual(controlled_negative_preflight({},None,None,enabled=False),(None,None))
            compile.assert_not_called()
            with self.assertRaisesRegex(ValueError,'obsolete negative'):
                controlled_negative_preflight({},None,None,enabled=True)
    def test_host_reopens_exact_approval_and_keeps_per_run_cap(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'campaign.json'
            ledger=self.setup_ledger(path)
            extend_approved_batch(path,expected_count=59,batch_id='first',approval='human +10')
            before=path.read_bytes()
            reopened=CampaignLedger.open_existing_approved(path,run_request_cap=2)
            self.assertEqual(reopened.state['max_requests'],69)
            self.assertEqual(path.read_bytes(),before)
            rate=dict(input_per_million='0.1',output_per_million='0.3',context_tokens=1000,
                      source='https://provider.test/models')
            reopened.register_verified_rate('fake-model',rate)
            body=dict(model='fake-model',max_tokens=100)
            for _ in range(2):
                identity=reopened.reserve(body);reopened.settle(identity,status='outcome_unknown')
            with self.assertRaisesRegex(ProviderConfigurationError,'run request limit'):
                reopened.reserve(body)
            self.assertEqual(len(reopened.state['requests']),61)
            self.assertFalse(reopened.lock_path.exists())

    def test_host_reopens_fifty_without_reset_and_rejects_tampered_approval(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'campaign.json'
            self.setup_ledger(path)
            extend_approved_batch(path,expected_count=59,batch_id='fifty',approval='human +50',new_batch_cap=50)
            good=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(CampaignLedger.open_existing_approved(path).state['max_requests'],109)
            mutations=[lambda s:s.update(max_requests=110),lambda s:s.update(limit_usd='2.00'),
                lambda s:s['additional_batch_approvals'][0].update(new_batch_cap=101),
                lambda s:s['requests'][0].update(charged_or_reserved_usd='0'),
                lambda s:s['additional_batch_approvals'][0].update(old_max_requests=61),
                lambda s:s.update(additional_batch_approvals=[])]
            for mutate in mutations:
                bad=deepcopy(good);mutate(bad)
                path.write_text(json.dumps(bad),encoding='utf-8')
                before=path.read_bytes()
                with self.assertRaises(ProviderConfigurationError):CampaignLedger.open_existing_approved(path)
                self.assertEqual(path.read_bytes(),before)

    def test_host_reopen_requires_existing_file_and_rejects_pending_dispatch(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'campaign.json'
            with self.assertRaises(FileNotFoundError):CampaignLedger.open_existing_approved(path)
            self.assertFalse(path.exists())
            ledger=self.setup_ledger(path)
            self.assertEqual(CampaignLedger.open_existing_approved(path).state['max_requests'],60)
            ledger.lock_path.write_text('foreign lock',encoding='utf-8')
            with self.assertRaisesRegex(ProviderConfigurationError,'pending'):
                CampaignLedger.open_existing_approved(path)
            self.assertEqual(ledger.lock_path.read_text(),'foreign lock')

    def test_explicit_fifty_approval_is_idempotent_and_preserves_prior_history(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'campaign.json'
            ledger=self.setup_ledger(path)
            original=deepcopy(ledger.state)
            receipt=extend_approved_batch(path,expected_count=59,batch_id='fifty',
                approval='human additional 50, same USD1',new_batch_cap=50)
            state=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(state['max_requests'],109)
            self.assertEqual(state['requests'],original['requests'])
            for key in ('approval','rates','limit_usd','created_at'):
                self.assertEqual(state[key],original[key])
            before=path.read_bytes()
            self.assertEqual(extend_approved_batch(path,expected_count=59,batch_id='fifty',
                approval='human additional 50, same USD1',new_batch_cap=50),receipt)
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'IDENTITY_CHANGED'):
                extend_approved_batch(path,expected_count=59,batch_id='fifty',
                    approval='human additional 50, same USD1',new_batch_cap=49)
            for cap in (0,101,True):
                with self.assertRaises(ValueError):extend_approved_batch(path,
                    expected_count=59,batch_id='bad',approval='human',new_batch_cap=cap)
            self.assertEqual(path.read_bytes(),before)

    def setup_ledger(self, path):
        ledger = CampaignLedger(path, approval='original-human-budget', rates={}, max_requests=60)
        ledger.state['requests'] = [dict(attempt_id=str(n), finished_at='finished',
            status='outcome_unknown', charged_or_reserved_usd='.001') for n in range(59)]
        ledger._write()
        return ledger

    def test_hundred_adds_to_unused_allowance_and_preserves_all_prior_records(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'campaign.json'
            self.setup_ledger(path)
            extend_approved_batch(path,expected_count=59,batch_id='ten',approval='human +10')
            state=json.loads(path.read_text())
            state['requests'].extend(dict(attempt_id=str(n),finished_at='finished',
                status='outcome_unknown',charged_or_reserved_usd='.001') for n in range(59,69))
            path.write_text(json.dumps(state))
            extend_approved_batch(path,expected_count=69,batch_id='fifty',approval='human +50',new_batch_cap=50)
            state=json.loads(path.read_text())
            state['requests'].extend(dict(attempt_id=str(n),finished_at='finished',
                status='received',charged_or_reserved_usd='.001') for n in range(69,97))
            path.write_text(json.dumps(state))
            original=deepcopy(state)
            receipt=extend_approved_batch(path,expected_count=97,batch_id='hundred',approval='human +100',
                new_batch_cap=100,carry_unused_allowance=True)
            self.assertEqual(receipt['carry_forward_remaining'],22)
            self.assertEqual(receipt['new_max_requests'],219)
            reopened=CampaignLedger.open_existing_approved(path,run_request_cap=3)
            self.assertEqual(reopened.state['requests'],original['requests'])
            for key in ('rates','approval','limit_usd','created_at'):
                self.assertEqual(reopened.state[key],original[key])
            self.assertEqual(remaining_approved_allowance(path,expected_count=97,cap=5),5)
            before=path.read_bytes()
            self.assertEqual(extend_approved_batch(path,expected_count=97,batch_id='hundred',approval='human +100',
                new_batch_cap=100,carry_unused_allowance=True),receipt)
            self.assertEqual(path.read_bytes(),before)
            bad=json.loads(before);bad['additional_batch_approvals'][-1]['carry_forward_remaining']=23
            path.write_text(json.dumps(bad))
            with self.assertRaises(ProviderConfigurationError):CampaignLedger.open_existing_approved(path)

    def test_explicit_batch_keeps_old_requests_dollars_rates_and_unknown_charges(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'campaign.json'
            original = deepcopy(self.setup_ledger(path).state)
            receipt = extend_approved_batch(path, expected_count=59, batch_id='new-batch', approval='human +10 USD1')
            current = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(current['requests'], original['requests'])
            for field in ('approval', 'rates', 'limit_usd', 'created_at'):
                self.assertEqual(current[field], original[field])
            self.assertEqual(receipt['old_max_requests'], 60)
            self.assertEqual(current['max_requests'], 69)
            self.assertEqual(receipt['new_batch_cap'], 10)
            before = path.read_bytes()
            self.assertEqual(extend_approved_batch(path, expected_count=59, batch_id='new-batch',
                approval='human +10 USD1'), receipt)
            self.assertEqual(path.read_bytes(), before)

    def test_changed_count_or_pending_attempt_cannot_extend(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'campaign.json'
            ledger = self.setup_ledger(path)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'CAMPAIGN_CHANGED_OR_PENDING'):
                extend_approved_batch(path, expected_count=58, batch_id='x', approval='yes')
            self.assertEqual(path.read_bytes(), before)
            ledger.state['requests'][0].pop('finished_at')
            ledger._write()
            with self.assertRaisesRegex(ValueError, 'CAMPAIGN_CHANGED_OR_PENDING'):
                extend_approved_batch(path, expected_count=59, batch_id='x', approval='yes')
            self.assertFalse(ledger.lock_path.exists())

    def test_no_approval_or_existing_lock_never_changes_budget(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'campaign.json'
            ledger = self.setup_ledger(path)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'APPROVAL_REQUIRED'):
                extend_approved_batch(path, expected_count=59, batch_id='x', approval='')
            ledger.lock_path.write_text('owned-other-process', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                extend_approved_batch(path, expected_count=59, batch_id='x', approval='yes')
            self.assertEqual(ledger.lock_path.read_text(encoding='utf-8'), 'owned-other-process')
            self.assertEqual(path.read_bytes(), before)

    def test_local_cap_counts_rejected_dispatches_and_is_not_ten_jobs(self):
        class Real:
            calls = []
            async def complete(self, body, token, config):
                self.calls.append('dispatched')
                raise RuntimeError('request rejected')
        real = Real()
        limited = LimitedTransport(real, 10)
        for _ in range(10):
            with self.assertRaisesRegex(RuntimeError, 'rejected'):
                asyncio.run(limited.complete({}, None, None))
        with self.assertRaisesRegex(ValueError, 'REQUEST_CAP_REACHED'):
            asyncio.run(limited.complete({}, None, None))
        self.assertEqual(len(real.calls), 10)
        for allowance in (0, 11, True):
            with self.assertRaises(ValueError):
                LimitedTransport(real, allowance)

    def test_resume_uses_only_existing_remaining_five_without_writing(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'campaign.json'
            self.setup_ledger(path)
            extend_approved_batch(path,expected_count=59,batch_id='approved',approval='human +10 USD1')
            state=json.loads(path.read_text(encoding='utf-8'))
            state['requests'].extend(dict(attempt_id=str(n),finished_at='finished',
                status='received',charged_or_reserved_usd='.001') for n in range(59,64))
            path.write_text(json.dumps(state),encoding='utf-8')
            before=path.read_bytes()
            self.assertEqual(remaining_approved_allowance(path,expected_count=64,cap=5),5)
            for count,cap in ((63,5),(64,6),(64,True)):
                with self.assertRaises(ValueError):remaining_approved_allowance(path,expected_count=count,cap=cap)
            self.assertEqual(path.read_bytes(),before)
            state['requests'].extend(dict(attempt_id=str(n),finished_at='finished') for n in range(64,69))
            path.write_text(json.dumps(state),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'EXHAUSTED'):
                remaining_approved_allowance(path,expected_count=69,cap=5)


if __name__ == '__main__':
    unittest.main()
