# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only response audit, optional exclusive summary output; never inference."""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest
from uuid import uuid4

from scripts.diagnose_model_schema_live import (OUT, ORIGINAL, PRIOR_LEDGER, CASES,
    build_case, load_original, validate, save, DiagnosticLedger, NANO, _shape_issues, checked_structure)

def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def audit():
    campaign = json.loads((OUT/'campaign.json').read_text(encoding='utf-8'))
    scope = json.loads((OUT/'scope.json').read_text(encoding='utf-8'))
    prior = json.loads(PRIOR_LEDGER.read_text(encoding='utf-8'))
    assert scope['source_sha256'] == hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()
    assert scope['prior_ledger_sha256'] == hashlib.sha256(PRIOR_LEDGER.read_bytes()).hexdigest()
    assert len(campaign['requests']) == len(CASES) == 8
    assert not (OUT/'campaign.dispatch-lock').exists()
    rows = []
    for case in CASES:
        result = json.loads((OUT/case/'result.json').read_text(encoding='utf-8'))
        attempt = result['attempt_id']
        evidence = OUT/case/'evidence'
        request = json.loads((evidence/'dispatches'/f'{attempt}.json').read_text(encoding='utf-8'))
        response = json.loads((evidence/f'{attempt}.json').read_text(encoding='utf-8'))
        record = json.loads((evidence/'validations'/f'{attempt}-{case}.json').read_text(encoding='utf-8'))
        assert sha(request['request_redacted']) == request['stored_request_sha256']
        assert sha(response['response_redacted']) == response['stored_response_sha256']
        assert sha(record['record_redacted']) == record['stored_record_sha256']
        assert not request['request_truncated'] and not response['response_truncated'] and not record['record_truncated']
        assert request['execution_id'] == response['execution_id'] == record['execution_id'] == result['execution_id']
        assert request['span_id'] == response['span_id'] == record['span_id']
        actual_wire = json.loads(request['request_redacted'])
        assert sha(json.dumps(actual_wire, sort_keys=True)) == request['request_sha256'] == response['request_sha256']
        assert sha(json.dumps(actual_wire['response_format'], sort_keys=True)) == request['schema_sha256']
        wire, original, observation, generation_request = build_case(case)
        assert actual_wire == wire
        candidate = json.loads(json.loads(response['response_redacted'])['choices'][0]['message']['content'])
        judgment = validate(case, candidate, wire, original, observation, generation_request)
        # Tuple/list JSON normalization is intentional for the small role probe.
        assert json.loads(json.dumps(judgment)) == result['validation']
        paid = next(r for r in campaign['requests'] if r['attempt_id'] == attempt)
        assert paid['status'] == 'received' and paid['finished_at'] and paid['charged_or_reserved_usd'] == result['estimated_usd']
        issues = judgment.get('host_issues', {})
        issues = issues.get('issues', []) if isinstance(issues, dict) else []
        rows.append(dict(case=case, execution_id=result['execution_id'], attempt_id=attempt,
            elapsed_s=result['elapsed_s'], completion_tokens=result['usage']['completion_tokens'],
            estimated_usd=result['estimated_usd'], finish_reason=result['finish_reason'],
            wire_shape_pass=not judgment['wire_issues'], acceptance_pass=judgment.get('host_pass', judgment.get('role_probe_pass')),
            category_coverage=(8-len(judgment['missing_category_coverage'])) if 'missing_category_coverage' in judgment else None,
            issue_codes=sorted(set(i['code'] for i in issues)), issue_count=len(issues),
            inventory_count=len(candidate.get('inventory', [])), trailing_whitespace=result['trailing_whitespace_chars']))
    new_cost = sum((Decimal(r['charged_or_reserved_usd']) for r in campaign['requests']), Decimal(0))
    prior_cost = sum((Decimal(r['charged_or_reserved_usd']) for r in prior['requests']), Decimal(0))
    assert new_cost+prior_cost < 1 and len(prior['requests'])+len(rows) == 10
    return dict(status='AUDIT_PASS_NOT_MODEL_ACCEPTANCE', rows=rows, new_calls=len(rows), total_calls_including_prior=10,
        new_estimated_usd=str(new_cost), total_estimated_usd=str(new_cost+prior_cost),
        new_elapsed_inference_s=round(sum(r['elapsed_s'] for r in rows), 3),
        unknown=0, raw_truncated=0, settings_written=False, prior_evidence_unchanged=True,
        caveat='First three root traces recorded receipt/validation completion as succeeded despite failed acceptance. '
               'Immutable raw kept; this audit records all acceptance failures. Subsequent harness root traces corrected.',
        photos_uploaded=0, robot_commands=0, isaac_commands=0, full_scene_pass=False)

class DiagnosticTests(unittest.TestCase):
    def test_original_contract_satisfiable(self):
        wire, observation, request = load_original()
        inventory = [{'id': row['id'], 'kind': row['category'], 'source': {
            'basis': 'visual', 'observation_ids': [row['id']], 'user_quote': None}}
            for row in observation.entities if row['role'] in ('object', 'unknown')]
        witness = {'summary': 'Offline schema witness, not a model output.',
                   'room': {'width_m': 4, 'length_m': 4, 'height_m': 2.5}, 'inventory': inventory}
        self.assertEqual([], _shape_issues(witness, wire['response_format']['json_schema']['schema']))
        checked_structure(witness, request, observation)
        for case in ('gpt_original', 'nano_flat', 'nano_normalized', 'nano_visual_first'):
            body, _, _, _ = build_case(case)
            self.assertEqual([], _shape_issues(witness, body['response_format']['json_schema']['schema']))

    def test_initial_comparisons_same_messages(self):
        for case in ('gpt_original', 'nano_flat', 'nano_normalized', 'nano_visual_first'):
            body, original, _, _ = build_case(case)
            self.assertEqual(original['messages'], body['messages'])

    def test_repairs_identical_feedback_and_schema(self):
        gpt, _, _, _ = build_case('gpt_repair_common')
        nano, _, _, _ = build_case('nano_repair_common')
        self.assertEqual(gpt['messages'], nano['messages'])
        self.assertEqual(gpt['response_format'], nano['response_format'])

    def test_schema_visibility_only_appends_contract(self):
        body, _, _, _ = build_case('nano_schema_in_prompt')
        base, _, _, _ = build_case('nano_normalized')
        self.assertEqual(base['messages'][1:], body['messages'][1:])
        self.assertTrue(body['messages'][0]['content'].startswith(base['messages'][0]['content']))
        self.assertEqual(base['response_format'], body['response_format'])

    def test_next_call_accounting_rejected_without_http(self):
        state = json.loads((OUT/'campaign.json').read_text(encoding='utf-8'))
        # Retain the isolated test copy under this campaign; no temp ACL edits,
        # recursive cleanup or production-ledger writes.
        path = OUT/'offline-ledger-checks'/uuid4().hex/'campaign.json'
        save(path, state)
        ledger = DiagnosticLedger(path, approval=state['approval'], rates=state['rates'],
                                  limit_usd=state['limit_usd'], max_requests=8)
        body, _, _, _ = build_case('nano_normalized')
        with self.assertRaisesRegex(Exception, 'limit reached'):
            ledger.reserve(body)
        self.assertEqual(8, len(json.loads(path.read_text())['requests']))

    def test_known_grouped_category_coverage_hole_remains_detected(self):
        wire, observation, request = load_original()
        witness = {'summary': 'Offline counterexample, never a live output.',
            'room': {'width_m': 4, 'length_m': 4, 'height_m': 2.5}, 'inventory': [
                {'id': 'a', 'kind': 'bed', 'source': {'basis': 'visual', 'observation_ids': ['e3', 'e4', 'e5'], 'user_quote': None}},
                {'id': 'b', 'kind': 'wardrobe', 'source': {'basis': 'visual', 'observation_ids': ['e6', 'e7', 'e8'], 'user_quote': None}},
                {'id': 'c', 'kind': 'cable_bundle', 'source': {'basis': 'visual', 'observation_ids': ['e9', 'e11'], 'user_quote': None}}]}
        result = validate('nano_normalized', witness, wire, wire, observation, request)
        self.assertTrue(result['host_pass'])  # Reproduces existing product weakness; not a desired contract.
        self.assertEqual(5, len(result['missing_category_coverage']))
        self.assertEqual(5, len(result['mismatched_category_refs']))

    def test_all_saved_evidence_and_counts(self):
        self.assertEqual(8, audit()['new_calls'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save-audit', action='store_true')
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiagnosticTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    summary = audit()
    if args.save_audit:
        save(OUT/'audit.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
