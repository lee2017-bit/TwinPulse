# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline timeout/reporting regression. No credentials or external inference."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from scripts.compare_model_roles_live import role_attempt_snapshot, role_terminal_stop, run_case, LUNA
from scripts.benchmark_role_campaign import bounded_role_case, execute
from twinpulse_provider.errors import ProviderTimeoutError


class RoleSettlementTests(unittest.TestCase):
    def ledger(self, root, status='outcome_unknown', finished=False):
        row=dict(attempt_id='a'*32,model_id='fixture/model',status=status,
                 charged_or_reserved_usd='.0764288')
        if finished:
            row['finished_at']='fixture'
        return SimpleNamespace(state=dict(requests=[row]),lock_path=root/'absent.lock')

    def test_pending_raw_keeps_full_reservation_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=self.ledger(root);before=deepcopy(ledger.state)
            attempts,errors=role_attempt_snapshot(['a'*32],root,ledger)
            self.assertEqual(attempts[0]['estimated_or_reserved_usd'],'.0764288')
            self.assertEqual(errors[0]['code'],'EVIDENCE_PENDING')
            self.assertEqual(role_terminal_stop({},attempts,errors,ledger),'REMOTE_UNKNOWN')
            self.assertEqual(ledger.state,before)
            self.assertEqual(list(root.iterdir()),[])

    def test_partial_json_stops_without_empty_response_classification(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/('a'*32+'.json')).write_text('{',encoding='utf-8')
            ledger=self.ledger(root,'received',True)
            attempts,errors=role_attempt_snapshot(['a'*32],root,ledger)
            self.assertEqual(errors[0]['code'],'EVIDENCE_UNREADABLE')
            self.assertIsNone(attempts[0]['finish_reason'])
            self.assertEqual(role_terminal_stop({},attempts,errors,ledger),'EVIDENCE_INCOMPLETE')

    def test_raw_received_but_ledger_unsettled_still_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=self.ledger(root)
            (root/('a'*32+'.json')).write_text(json.dumps(dict(status='received',finish_reason='stop')),encoding='utf-8')
            attempts,errors=role_attempt_snapshot(['a'*32],root,ledger)
            self.assertEqual(errors,[])
            self.assertEqual(role_terminal_stop({},attempts,errors,ledger),'REMOTE_UNKNOWN')

    def test_output_limit_and_402_facts_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=self.ledger(root,'rejected',True)
            (root/('a'*32+'.json')).write_text(json.dumps(dict(status='rejected',http_status=402,
                response_redacted=json.dumps(dict(error=dict(code='payment_required'),choices=[dict(finish_reason='length')])))),encoding='utf-8')
            attempts,errors=role_attempt_snapshot(['a'*32],root,ledger)
            self.assertEqual(attempts[0]['http_status'],402)
            self.assertEqual(attempts[0]['provider_error_code'],'payment_required')
            self.assertEqual(role_terminal_stop({},attempts,errors,ledger),'OUTPUT_LIMIT')

    def test_missing_ledger_never_becomes_zero_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=self.ledger(root);ledger.state['requests']=[]
            with self.assertRaisesRegex(ValueError,'LEDGER_ATTEMPT_MISSING'):
                role_attempt_snapshot(['a'*32],root,ledger)

    def test_finished_received_no_false_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ledger=self.ledger(root,'received',True)
            (root/('a'*32+'.json')).write_text(json.dumps(dict(status='received',finish_reason='stop')),encoding='utf-8')
            attempts,errors=role_attempt_snapshot(['a'*32],root,ledger)
            self.assertIsNone(role_terminal_stop({},attempts,errors,ledger))


class RoleTimeoutPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_run_case_tail_saves_timeout_before_late_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);photo=root/'fixture.jpg';photo.write_bytes(b'offline fixture not sent')
            ledger=RoleSettlementTests().ledger(root)
            ledger.state['requests'][0]['model_id']=LUNA['model_id']
            transport=SimpleNamespace(calls=['a'*32],record_validation=Mock())
            service=SimpleNamespace(generate=AsyncMock(side_effect=ProviderTimeoutError('offline timeout')))
            with patch('scripts.compare_model_roles_live.AuditedChatTransport',return_value=transport), \
                 patch('scripts.compare_model_roles_live.GenerationService',return_value=service):
                row=await run_case(root/'case','planner',LUNA,1,dict(openai=SimpleNamespace(load=lambda:'unused-offline')),
                    ledger,None,dict(photo_sha256='fixture',observation_sha256='fixture'),photo=photo,prompt='fixture',output_cap=40000)
            directory=root/'case/cases'/row['case_id']
            self.assertEqual(row['status'],'FAIL')
            self.assertEqual(row['failure_code'],'PROVIDER_TIMEOUT')
            self.assertEqual(row['terminal_stop'],'REMOTE_UNKNOWN')
            self.assertEqual(row['actual_calls'],1)
            self.assertEqual(row['estimated_or_reserved_usd'],'0.0764288')
            self.assertEqual(row['evidence_errors'][0]['code'],'EVIDENCE_PENDING')
            self.assertEqual(json.loads((directory/'result.json').read_text(encoding='utf-8')),row)
            self.assertFalse((directory/'evidence'/('a'*32+'.json')).exists())
            # A later worker result cannot rewrite the already-failed snapshot.
            (directory/'evidence').mkdir(exist_ok=True)
            (directory/'evidence'/('a'*32+'.json')).write_text('{}',encoding='utf-8')
            self.assertEqual(json.loads((directory/'result.json').read_text(encoding='utf-8'))['status'],'FAIL')
            service.generate.assert_awaited_once()

    async def test_unexpected_report_error_has_exclusive_interruption_record_no_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);runner=AsyncMock(side_effect=FileNotFoundError('offline missing raw'))
            row,failure=await bounded_role_case(root,dict(job_id='fixture'),runner)
            self.assertIsNone(row)
            self.assertFalse(failure['automatic_retry'])
            self.assertEqual(failure['status'],'HOST_REPORT_ABORTED')
            self.assertTrue((root/'interrupted-job.json').exists())
            self.assertFalse((root/'result.json').exists())
            runner.assert_awaited_once()

    async def test_normal_case_unmodified_and_cancellation_not_hidden(self):
        import asyncio
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);expected=dict(status='PASS')
            row,error=await bounded_role_case(root,{},AsyncMock(return_value=expected))
            self.assertIs(row,expected);self.assertIsNone(error)
            with self.assertRaises(asyncio.CancelledError):
                await bounded_role_case(root,{},AsyncMock(side_effect=asyncio.CancelledError()))
            self.assertFalse((root/'interrupted-job.json').exists())

    async def test_campaign_report_exception_writes_stopped_summary_and_no_next_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);photo=root/'fixture.jpg';photo.write_bytes(b'not sent')
            spec=root/'spec.json';spec.write_text('{}',encoding='utf-8')
            case=dict(case_id='fixture-room',room_group='fixture-room',photo=str(photo),
                      photo_sha256='fixture',prompt='fixture',prompt_sha256='fixture',source={})
            runner=AsyncMock(side_effect=FileNotFoundError('offline reporting fault'))
            fake_ledger=SimpleNamespace(state=dict(requests=[]),lock_path=root/'absent.lock')
            args=SimpleNamespace(output=root/'output',spec=spec,existing_nebius='1',existing_openai='1')
            with patch('scripts.benchmark_role_campaign.DEADLINE','2099-01-01T00:00:00+00:00'), \
                 patch('scripts.benchmark_role_campaign.public_cases',return_value=[case]), \
                 patch('scripts.benchmark_role_campaign.credentials',return_value=({'nebius':object(),'openai':object()},{})), \
                 patch('scripts.benchmark_role_campaign.metadata_get',side_effect=[([], 'fixture'),({'data':[]},'fixture'),({'data':[{'id':'gpt-6-luna'}]},'fixture')]), \
                 patch('scripts.benchmark_role_campaign.catalog_from_inventory',return_value={}), \
                 patch('scripts.benchmark_role_campaign.source_freeze',return_value={'fixture':1}), \
                 patch('scripts.benchmark_role_campaign.ComparisonLedger',return_value=fake_ledger), \
                 patch('scripts.benchmark_role_campaign.sha',return_value='fixture'), \
                 patch('scripts.benchmark_role_campaign.run_case',runner):
                await execute(args)
            summary=json.loads((args.output/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['status'],'STOPPED')
            self.assertEqual(summary['stop_reason'],'HOST_REPORT_ABORTED')
            self.assertEqual(summary['ended'],0)
            self.assertIsNotNone(summary['interrupted_job'])
            self.assertFalse(summary['whole_demo_pass'])
            self.assertFalse((args.output/'owner.lock').exists())
            runner.assert_awaited_once()


if __name__=='__main__':unittest.main()
