# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline financial admission/raw boundary; not actual model acceptance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.progressive_functional_scope import audit_runtime, reserve, canonical_sha, exclusive, host_finance_supplement, read_host_finance_supplement


class FunctionalScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.root=Path(self.directory.name)
        self.scope=dict(expires_at='2026-10-11T22:33:20+00:00',additional_limit_usd='10',
            cases=[dict(case_id='text',reservation_usd='2',request_limit=13),
                   dict(case_id='photo',reservation_usd='1',request_limit=12)])
        self.finance=self.root/'finance.json'
        self.write_state([])
        self.clock=patch('scripts.progressive_functional_scope.datetime')
        clock=self.clock.start()
        clock.now.return_value=datetime(2026,10,11,16,tzinfo=timezone.utc)
        clock.fromisoformat.side_effect=datetime.fromisoformat
        self.addCleanup(self.clock.stop)
        self.addCleanup(self.directory.cleanup)

    def write_state(self,runs):
        self.finance.write_text(json.dumps(dict(scope_sha256=canonical_sha(self.scope),runs=runs)),encoding='utf-8')

    def prior(self,**changes):
        return dict(case_id='text',settled=True,estimated_usd='0.1',held_usd='0',unknown_requests=0,**changes)

    def test_reserve_is_written_before_dispatch_and_duplicate_is_rejected(self):
        reserve(self.scope,self.finance,'text')
        row=json.loads(self.finance.read_text())['runs'][0]
        self.assertFalse(row['settled']);self.assertEqual(row['held_usd'],'2')
        with self.assertRaisesRegex(ValueError,'ALREADY_DISPATCHED'):reserve(self.scope,self.finance,'text')

    def test_unsettled_unknown_and_held_block_next_dispatch(self):
        for changes,reason in ((dict(settled=False),'UNSETTLED'),(dict(unknown_requests=1),'UNKNOWN'),(dict(held_usd='.2'),'UNKNOWN')):
            row=self.prior();row.update(changes);self.write_state([row])
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,reason):reserve(self.scope,self.finance,'photo')

    def test_budget_and_invalid_amount_do_not_mutate_finance(self):
        for amount,reason in (('9.5','BUDGET_EXCEEDED'),('-1','INVALID_FINANCIAL'),('NaN','INVALID_FINANCIAL')):
            row=self.prior();row['estimated_usd']=amount;self.write_state([row]);before=self.finance.read_bytes()
            with self.subTest(amount=amount),self.assertRaisesRegex(ValueError,reason):reserve(self.scope,self.finance,'photo')
            self.assertEqual(self.finance.read_bytes(),before)

    def test_deadline_and_terminal_stop_block(self):
        state=json.loads(self.finance.read_text());state['stop_reason']='OUTPUT_LENGTH_STOP'
        self.finance.write_text(json.dumps(state),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'GATED_STOP'):reserve(self.scope,self.finance,'photo')
        self.write_state([])
        with patch('scripts.progressive_functional_scope.datetime') as clock:
            clock.now.return_value=datetime(2026,10,11,22,10,tzinfo=timezone.utc)
            clock.fromisoformat.side_effect=datetime.fromisoformat
            with self.assertRaisesRegex(ValueError,'DEADLINE'):reserve(self.scope,self.finance,'photo')

    def test_prior_source_cohort_cost_is_not_reset(self):
        self.scope['prior_new_exposure_usd']='9.5';self.write_state([])
        state=json.loads(self.finance.read_text());state['prior_new_exposure_usd']='9.5'
        self.finance.write_text(json.dumps(state),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'BUDGET_EXCEEDED'):reserve(self.scope,self.finance,'photo')
        state['prior_new_exposure_usd']='0';self.finance.write_text(json.dumps(state),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'PRIOR_EXPOSURE_CHANGED'):reserve(self.scope,self.finance,'photo')

    def raw_fixture(self,*,usage=True,status='received'):
        ordinary=self.root/'ordinary-generation';evidence=self.root/'provider-evidence'
        ordinary.mkdir();(evidence/'dispatches').mkdir(parents=True);(evidence/'validations').mkdir()
        digest=lambda text:hashlib.sha256(text.encode()).hexdigest()
        identity=dict(request_sha256='request',schema_sha256='schema',execution_id='execution')
        request=dict(attempt_id='attempt',status=status,usage=dict(input_tokens=3,output_tokens=2) if usage else None,
            charged_or_reserved_usd='.02',finished_at='2026-10-11T16:00:00Z')
        exclusive(ordinary/'approval.ledger.json',dict(requests=[request]))
        raw=dict(**identity,status=status,usage=request['usage'],response_truncated=False,
            response_redacted='response',stored_response_sha256=digest('response'),role='planner',model_id='approved',
            finish_reason='stop',elapsed_s=2)
        exclusive(evidence/'attempt.json',raw)
        exclusive(evidence/'dispatches/attempt.json',dict(**identity,request_truncated=False,
            request_redacted='request',stored_request_sha256=digest('request')))
        exclusive(evidence/'validations/attempt-1.json',dict(record_truncated=False,attempt_id='attempt',
            execution_id='execution',record_redacted='validation',stored_record_sha256=digest('validation')))
        return ordinary,evidence

    def test_all_approval_ledgers_are_counted_without_zeroing_missing_usage(self):
        self.raw_fixture(usage=False,status='unknown')
        value=audit_runtime(self.root,request_limit=12,total_limit='1')
        self.assertEqual(value['estimated_usd'],'0');self.assertEqual(value['held_usd'],'0.02')
        self.assertEqual(value['unknown_requests'],1);self.assertFalse(value['invoice_verified'])

    def test_complete_response_is_estimated_not_invoice(self):
        self.raw_fixture()
        value=audit_runtime(self.root,request_limit=12,total_limit='1')
        self.assertEqual(value['estimated_usd'],'0.02');self.assertEqual(value['held_usd'],'0')
        self.assertEqual(value['request_count'],1)

    def test_duplicate_identity_or_raw_truncation_is_not_settled(self):
        ordinary,evidence=self.raw_fixture()
        exclusive(ordinary/'other.ledger.json',json.loads((ordinary/'approval.ledger.json').read_text()))
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):audit_runtime(self.root,request_limit=12,total_limit='1')
        (ordinary/'other.ledger.json').unlink()
        raw=json.loads((evidence/'attempt.json').read_text());raw['response_truncated']=True
        (evidence/'attempt.json').write_text(json.dumps(raw),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'RAW_FINANCIAL'):audit_runtime(self.root,request_limit=12,total_limit='1')

    def test_dispatch_and_request_caps_stop_audit(self):
        ordinary,_=self.raw_fixture();(ordinary/'owner.dispatch-lock').touch()
        with self.assertRaisesRegex(ValueError,'UNSETTLED'):audit_runtime(self.root,request_limit=12,total_limit='1')
        (ordinary/'owner.dispatch-lock').unlink()
        with self.assertRaisesRegex(ValueError,'CAP_EXCEEDED'):audit_runtime(self.root,request_limit=0,total_limit='1')
        with self.assertRaisesRegex(ValueError,'CAP_EXCEEDED'):audit_runtime(self.root,request_limit=12,total_limit='.01')

    def supplement_fixture(self):
        original=self.root
        directory=original/'outputs/progressive-twin-overnight-20261012/scope'
        runtime=directory/'text/runtime';runtime.mkdir(parents=True)
        self.root=runtime
        ordinary,evidence=self.raw_fixture()
        self.root=original
        validation=evidence/'validations/attempt-1.json';validation.unlink()
        ledger_path=ordinary/'approval.ledger.json';ledger=json.loads(ledger_path.read_text())
        ledger['rates']={'approved':dict(input_per_million='1000',output_per_million='1000')}
        request=ledger['requests'][0]
        request.update(model_id='approved',usage=dict(prompt_tokens=3,completion_tokens=2,total_tokens=5),
            charged_or_reserved_usd='.005',estimated_usd='.005')
        ledger_path.write_text(json.dumps(ledger),encoding='utf-8')
        exclusive(ordinary/'approval.ledger.ordinary-scope.json',dict(rates_sha256=canonical_sha(ledger['rates'])))
        raw_path=evidence/'attempt.json';raw=json.loads(raw_path.read_text())
        raw.update(usage=request['usage'],http_status=200,final_empty=False)
        raw_path.write_text(json.dumps(raw),encoding='utf-8')
        catalog_value=dict(models=[dict(model_id='approved',input_per_million='1000',output_per_million='1000')])
        exclusive(directory/'stage-model-catalog.json',catalog_value)
        catalog_digest=hashlib.sha256((directory/'stage-model-catalog.json').read_bytes()).hexdigest()
        scope=dict(models=dict(observer='observer',planner='approved'),
            settings_freeze={str(directory/'reviewed-settings/stage_model_catalog.json'):catalog_digest},
            cases=[dict(case_id='text',request_limit=12,reservation_usd='3')])
        scope_path=directory/'functional-scope.json';exclusive(scope_path,scope)
        exclusive(directory/'functional-finance.json',dict(scope_sha256=canonical_sha(scope),runs=[dict(
            case_id='text',product_status='FAIL',status='UNKNOWN',settled=False,audit_error_type='ValueError',
            held_usd='3',estimated_usd='0',unknown_requests=1)]))
        exclusive(directory/'text/result.json',dict(status='FAIL',financial_audit_error='ValueError',
            source_and_build_unchanged=True,scope_settings_unchanged=True,supervisor=dict(backend=dict(owned=False),engine=dict(owned=False))))
        return scope_path,scope,ordinary,evidence,runtime

    def test_supplement_preserves_full_hold_and_binds_all_raw_without_product_pass(self):
        path,scope,ordinary,evidence,runtime=self.supplement_fixture()
        original=(path.parent/'functional-finance.json').read_bytes()
        with patch('scripts.progressive_functional_scope.check_scope',return_value=scope):
            value=host_finance_supplement(path,self.root)
            self.assertEqual(value['protected_exposure_usd'],'3');self.assertEqual(value['estimated_wire_usd'],'0.005')
            self.assertEqual(value['original_product_status'],'FAIL');self.assertFalse(value['original_hold_released'])
            exclusive(path.parent/'host-finance-supplement.json',value)
            self.assertEqual(read_host_finance_supplement(path,self.root)[1],value)
            (ordinary/'approval.ledger.json').write_text((ordinary/'approval.ledger.json').read_text()+' ',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'EVIDENCE_CHANGED'):read_host_finance_supplement(path,self.root)
        self.assertEqual((path.parent/'functional-finance.json').read_bytes(),original)
        with self.assertRaisesRegex(ValueError,'VALIDATION_MISSING'):audit_runtime(runtime,request_limit=12,total_limit='3')

    def test_supplement_unknown_transport_or_incomplete_usage_remains_blocked(self):
        path,scope,ordinary,evidence,_=self.supplement_fixture()
        with patch('scripts.progressive_functional_scope.check_scope',return_value=scope):
            ledger_path=ordinary/'approval.ledger.json';raw_path=evidence/'attempt.json'
            ledger=json.loads(ledger_path.read_text());raw=json.loads(raw_path.read_text())
            ledger['requests'][0]['status']=raw['status']='unknown'
            ledger_path.write_text(json.dumps(ledger),encoding='utf-8');raw_path.write_text(json.dumps(raw),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'TYPED_DEFECT'):host_finance_supplement(path,self.root)
            ledger['requests'][0]['status']=raw['status']='received'
            ledger['requests'][0]['usage']=raw['usage']=dict(prompt_tokens=3,completion_tokens=2)
            ledger_path.write_text(json.dumps(ledger),encoding='utf-8');raw_path.write_text(json.dumps(raw),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'USAGE_INCOMPLETE'):host_finance_supplement(path,self.root)

    def test_supplement_orphan_prices_and_active_owner_cannot_open_guard(self):
        path,scope,ordinary,evidence,_=self.supplement_fixture()
        with patch('scripts.progressive_functional_scope.check_scope',return_value=scope):
            orphan=evidence/'extra.json';exclusive(orphan,{})
            with self.assertRaisesRegex(ValueError,'ORPHAN'):host_finance_supplement(path,self.root)
            orphan.unlink();catalog=path.parent/'stage-model-catalog.json'
            value=json.loads(catalog.read_text());value['models'][0]['input_per_million']='1001'
            catalog.write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'CATALOG_NOT_ORIGINALLY_FROZEN'):host_finance_supplement(path,self.root)
            (path.parent/'functional-owner.lock').touch()
            with self.assertRaisesRegex(ValueError,'OWNER_OR_SCOPE'):host_finance_supplement(path,self.root)


if __name__=='__main__':unittest.main()
