# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No external calls, credentials, browser, files or physical activity."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import verify_semantic_scoped_live_recovery as runner


class Delegate:
    def __init__(self):
        self.calls = []
        self.validations = []
        self.answer = object()

    async def complete(self, body, token, config):
        self.calls.append((body, token, config))
        return self.answer

    def record_validation(self, *args):
        self.validations.append(args)


class RecoveryHarnessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.delegate = Delegate()
        self.body = {'model': runner.NANO, 'max_tokens': 20000,
            'messages': [{'role': 'user', 'content': 'JSON correction'}],
            'response_format': {'json_schema': {'name': 'twinpulse_semantic_structure'}}}
        self.config = object()
        response = {'id': 'local-fixture-only', 'model': runner.NANO, 'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps({'original': True})}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
        self.data = {'records': [{'model_id': runner.NANO, 'response_redacted': json.dumps(response),
            'attempt_id': 'prior-attempt', 'stored_response_sha256': 'prior-hash'}],
            'fault_index': 0, 'failed': {'injected': True}}
        self.wrapper = runner.ReplayInitialLiveRepairs(self.delegate, self.data, Path('unused-test-path'))

    async def test_initial_is_marked_fixture_never_http(self):
        original = deepcopy(self.data)
        with patch.object(runner, 'save') as saved:
            completion = await self.wrapper.complete(self.body, SimpleNamespace(generation_role='initial'), self.config)
        self.assertEqual(json.loads(completion.content), {'injected': True})
        self.assertEqual(self.delegate.calls, [])
        self.assertEqual(self.data, original)
        record = saved.call_args.args[1]
        self.assertTrue(record['fixture'])
        self.assertFalse(record['external_http'])
        self.assertEqual(record['source_attempt_id'], 'prior-attempt')

    async def test_approved_repair_reaches_original_transport(self):
        token = SimpleNamespace(generation_role='repair')
        result = await self.wrapper.complete(self.body, token, self.config)
        self.assertIs(result, self.delegate.answer)
        self.assertEqual(self.delegate.calls, [(self.body, token, self.config)])
        self.assertEqual(self.wrapper.index, 0)

    async def assert_rejected_before_dispatch(self, body, role='repair'):
        with self.assertRaises(ValueError):
            await self.wrapper.complete(body, SimpleNamespace(generation_role=role), self.config)
        self.assertEqual(self.delegate.calls, [])

    async def test_other_model_rejected(self):
        await self.assert_rejected_before_dispatch({**self.body, 'model': 'gpt-test'})

    async def test_other_output_cap_rejected(self):
        await self.assert_rejected_before_dispatch({**self.body, 'max_tokens': 20001})

    async def test_image_leak_rejected(self):
        await self.assert_rejected_before_dispatch({**self.body,
            'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'image'}}]}]})

    async def test_other_schema_rejected(self):
        await self.assert_rejected_before_dispatch({**self.body,
            'response_format': {'json_schema': {'name': 'unapproved'}}})

    async def test_unknown_role_rejected(self):
        await self.assert_rejected_before_dispatch(self.body, role='diagnostic')

    async def test_fixture_validation_cannot_impersonate_paid_validation(self):
        self.wrapper.replayed.add('a'*32)
        with patch.object(self.wrapper.fixture_evidence, 'validation') as saved:
            self.wrapper.record_validation('structure', 'a'*32, {'validation': 'failed'})
        self.assertTrue(saved.call_args.args[2]['fixture'])
        self.assertFalse(saved.call_args.args[2]['external_http'])
        self.assertEqual(self.delegate.validations, [])
        self.wrapper.record_validation('structure', 'b'*32, {'validation': 'passed'})
        self.assertEqual(self.delegate.validations, [('structure', 'b'*32, {'validation': 'passed'})])


class CurrentAccountingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path('unused-current-grant')
        self.ledger_path = self.root/'run-1/runtime/ordinary-generation/current.ledger.json'
        self.ledger = {'max_requests': 10, 'limit_usd': '1.00',
            'requests': [{'finished_at': 'local-only', 'status': 'received'} for _ in range(6)]}
        self.generation = {'error': {'diagnostics': {'budget': {'stop_reason': 'REPAIR_STALLED'}}}}
        self.summary = {'status': 'FAIL', 'originals_unchanged': True,
            'ordinary_live_audit': {'locks_pending': 0, 'requests': 6,
                'rows': [{'raw_ledger_match': True, 'dispatch_sha_matches': True,
                    'validation_files': 1, 'finish_reason': 'stop'} for _ in range(6)]},
            'browser': {'terminal': {'conversation': {'generation': self.generation}}}}
        self.files = {self.root/'summary.json': self.summary,
            self.root/'approval.json': {'approval': 'current-human-grant'}, self.ledger_path: self.ledger}

    def load(self, expected='current-human-grant'):
        with patch.object(runner, 'read', side_effect=self.files.__getitem__), \
                patch.object(Path, 'glob', return_value=[self.ledger_path]), \
                patch.object(Path, 'exists', return_value=False):
            return runner.accounting_source(self.root, expected)

    def test_failed_natural_scene_does_not_reset_current_call_count(self):
        result = self.load()
        self.assertEqual(result['ledger_path'], self.ledger_path)
        self.assertEqual(len(result['ledger']['requests']), 6)
        self.assertEqual(10-len(result['ledger']['requests']), 4)
        self.assertEqual(result['summary']['status'], 'FAIL')

    def test_different_human_approval_rejected(self):
        with self.assertRaisesRegex(ValueError, 'approval/history'):
            self.load('old-human-grant')

    def test_unknown_or_unfinished_call_rejected(self):
        for change in ({'status': 'outcome_unknown'}, {'finished_at': None}):
            with self.subTest(change=change):
                original = dict(self.ledger['requests'][0])
                self.ledger['requests'][0].update(change)
                with self.assertRaises(ValueError): self.load()
                self.ledger['requests'][0] = original

    def test_campaign_wide_stop_is_not_bypassed_by_new_case(self):
        for code in ('PROVIDER_OUTPUT_TRUNCATED', 'REMOTE_OUTCOME_UNKNOWN', 'VALIDATION_EVIDENCE_FAILED'):
            with self.subTest(code=code):
                self.generation['error']['diagnostics']['budget']['stop_reason'] = code
                with self.assertRaises(ValueError): self.load()

    def test_damaged_or_length_evidence_rejected(self):
        row = self.summary['ordinary_live_audit']['rows'][0]
        for field, value in (('raw_ledger_match', False), ('dispatch_sha_matches', False),
                ('validation_files', 0), ('finish_reason', 'length')):
            with self.subTest(field=field):
                original = row[field]; row[field] = value
                with self.assertRaises(ValueError): self.load()
                row[field] = original

    def test_original_mutation_rejected(self):
        self.summary['originals_unchanged'] = False
        with self.assertRaises(ValueError): self.load()


class SavedGeometryAccountingTests(unittest.TestCase):
    """Read-only genuine recorded evidence, never network or a fresh success sample."""
    def setUp(self):
        self.source=runner.ROOT/'outputs/structure-repair-live-20261009-ten'
        self.previous=runner.ROOT/'outputs/structure-repair-controlled-20261009'
        self.current=runner.ROOT/'outputs/geometry-repair-live-20261009'

    def test_all_eight_previous_calls_deducted_not_only_six_natural_calls(self):
        budget=runner.with_remainder_history(runner.accounting_source(self.source),self.previous)
        self.assertEqual(len(budget['ledger']['requests']),8)
        self.assertEqual(10-len(budget['ledger']['requests']),2)

    def test_geometry_is_original_failure_not_injected_fixture(self):
        data=runner.context(self.source,'geometry')
        self.assertEqual(data['fault_index'],-1)
        self.assertEqual(len(data['records']),4)
        self.assertEqual(len(data['failed']['objects']),10)
        self.assertEqual(data['diagnosis']['issues'][0]['target_ids'],['window_blind_1'])

    def test_actual_patch_audit_reproduces_same_complete_plan(self):
        original=runner.sha(self.current/'geometry/result.json')
        data,plan,provenance,result,audit=runner.audited_geometry(self.current)
        self.assertEqual(audit['actual_model_calls'],9)
        self.assertEqual(audit['new_paid_calls'],1)
        self.assertEqual(audit['unused_calls'],1)
        self.assertEqual(runner.canonical_sha256(plan),result['compiled_plan_sha256'])
        self.assertEqual(original,runner.sha(self.current/'geometry/result.json'))

    def test_wrong_remainder_count_rejected_without_dispatch(self):
        ordinary_read=runner.read
        def bad_read(path):
            value=ordinary_read(path)
            if path==self.previous/'audit.json':value['actual_model_calls']=7
            return value
        with patch.object(runner,'read',side_effect=bad_read):
            with self.assertRaisesRegex(ValueError,'audit/count/cost'):
                runner.with_remainder_history(runner.accounting_source(self.source),self.previous)


if __name__ == '__main__':
    unittest.main()
