# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline production-path regression. Fixtures are not real-model acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))

import test_budgeted_generation as budget_fixtures
from test_budgeted_generation import (FixtureTransport, structure, wire_structure, bed,
    text_request, empty_observation, config, PLANNER_MODEL)
from test_scene_contract import observed
from test_photo_layout import request as photo_request
from twinpulse_provider import GenerationService, InvalidProviderResponseError
from twinpulse_provider.generation_policy import GenerationPolicy, ProgressTracker, diagnostic_blockers
from twinpulse_provider.semantic_scene import checked_structure, structure_schema, inventory_requirements
from twinpulse_provider.reliability import AuditedChatTransport, InferenceEvidence
from twinpulse_provider.generation_store import input_digest
from twinpulse_app.generation_scope import OrdinaryInferenceScope
from twinpulse_app.product_workflow_service import _public_generation_diagnostics
from twinpulse_core.execution_diagnostics import ExecutionStore
from twinpulse_core import canonical_sha256
from test_semantic_binding_repair import keyed


def photo_observation(*identities):
    return observed(*[(identity, 'bed', 'object', 'middle_right', .9) for identity in identities])


def visual_structure(*identities):
    value = structure()
    value['inventory'] = [dict(id=identity, kind='bed', source=dict(
        basis='visual', observation_ids=[identity], user_quote=None)) for identity in identities]
    return value


def bound_visual_structure(*identities):
    value = wire_structure()
    value['inventory'] = [dict(id=identity, kind='bed', evidence_ref='seen:'+identity) for identity in identities]
    return value


def binding_patch(candidate, *operations, request=None, obs=None):
    result = keyed(candidate, request, obs)
    for operation in operations:
        if operation['op'] in ('room', 'summary'):
            result[operation['op']] = deepcopy(operation['value'])
        elif operation['op'] == 'set':
            result['changes'][operation['id']] = {key: deepcopy(value) for key, value in operation.items() if key != 'id'}
        else:
            row = operation['value']
            result['additions'][row['evidence_ref'][5:]] = deepcopy(row)
    return result


class RepairEvidenceTests(unittest.TestCase):
    def provider(self, transport, **kwargs):
        return budget_fixtures.PipelineTests.provider(self, transport, **kwargs)

    def run_provider(self, provider, request=None):
        return asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2')
            .generate(request or text_request()))

    def test_photo_contract_dynamic_and_paths_are_inventory_only(self):
        for identities in (('a',), ('x', 'y', 'z', 'q'), tuple('item'+str(i) for i in range(14))):
            with self.subTest(identities=identities):
                observation = photo_observation(*identities)
                requirements = inventory_requirements(observation)
                self.assertEqual([row['observation_id'] for row in requirements], list(identities))
                schema = structure_schema(text_request(), observation)
                self.assertEqual(schema['properties']['inventory']['minItems'], (len(identities)+2)//3)
                with self.assertRaises(InvalidProviderResponseError) as caught:
                    checked_structure(structure(), text_request(), observation)
                issue = caught.exception.contract_report['issues'][-1]
                self.assertEqual(issue['path'], '$.inventory')
                self.assertEqual(issue['missing_ids'], sorted(identities))
                # Extra same-category objects requested only in text remain legal.
                value = visual_structure(*identities)
                value['inventory'].append(dict(id='extra', kind='bed', source=dict(
                    basis='user', observation_ids=[], user_quote='a bed')))
                self.assertEqual(checked_structure(value, text_request(), observation), value)
        self.assertEqual(structure_schema(text_request(), empty_observation())['properties']['inventory']['minItems'], 0)
        self.assertEqual(checked_structure({**structure(), 'inventory': []},
            text_request('An empty room'), empty_observation())['inventory'], [])

    def test_target_reduction_progress_not_summary_order_swapping_or_oscillation(self):
        tracker = ProgressTracker()
        def blockers(ids):
            return diagnostic_blockers({'issues': [dict(code='PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING',
                path='$.inventory', missing_ids=ids)]}, 'FALLBACK')
        first = {'inventory': [{'id': 'a'}, {'id': 'b'}], 'summary': 'old'}
        self.assertFalse(tracker.observe(first, blockers(list(range(14)))))
        changed = {**first, 'inventory': list(reversed(first['inventory'])), 'summary': 'new'}
        self.assertFalse(tracker.observe(changed, blockers(list(range(14)))))
        second = {'inventory': [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]}
        self.assertTrue(tracker.observe(second, blockers(list(range(7)))))
        third = {'inventory': [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}, {'id': 'd'}]}
        self.assertTrue(tracker.observe(third, blockers([0])))
        self.assertFalse(tracker.observe(first, blockers([0])))
        self.assertFalse(tracker.observe({'inventory': [{'id': 'e'}]}, blockers([1])))
        self.assertIn('BAD:$.inventory:invalid_ids:q', diagnostic_blockers(
            {'issues': [dict(code='BAD', path='$.inventory', invalid_ids=['q'])]}, 'FALLBACK'))

    def test_repair_contains_exact_candidate_latest_diagnosis_and_attempt_no_accumulation(self):
        bad = {**wire_structure(), 'summary': '', 'room': dict(width_m=13, length_m=6, height_m=2.6)}
        bad2 = {**bad, 'room': dict(width_m=7, length_m=6, height_m=2.6)}
        transport = FixtureTransport([bad, binding_patch(bad, dict(op='room', value=bad2['room'])),
            binding_patch(bad2, dict(op='summary', value='Estimated bedroom')), {'bed': bed()}])
        provider = self.provider(transport)
        self.run_provider(provider)
        attempts = provider.diagnostic_for('generation-test')['attempts']
        self.assertEqual([row['repair'] for row in attempts], [False, True, True, False])
        self.assertEqual(attempts[0]['validation_code'], 'SEMANTIC_ROOM_INVALID')
        self.assertNotIn('scene_contract', provider.diagnostic_for('generation-test'))
        self.assertNotIn('validation_code', provider.diagnostic_for('generation-test'))
        for index, candidate in ((1, bad), (2, bad2)):
            messages = transport.bodies[index]['messages']
            self.assertEqual([m['role'] for m in messages], ['system', 'user'])
            self.assertEqual(len(messages[-1]['content'].splitlines()), 2)
            feedback = json.loads(messages[-1]['content'].splitlines()[-1])
            self.assertEqual(feedback['previous_candidate'], candidate)
            self.assertEqual(feedback['previous_attempt_id'], attempts[index-1]['attempt_id'])
            self.assertEqual(feedback['validation']['issues'][0]['path'], '$.room' if index==1 else '$.summary')

    def test_photo_previous_candidate_and_request_local_coverage_are_transmitted(self):
        observation = photo_observation('new_bed')
        request = replace(photo_request(), prompt='a bed')
        bad = bound_visual_structure('new_bed')
        bad['inventory'][0]['kind'] = 'wardrobe'
        fix = binding_patch(bad, dict(op='set', id='new_bed', value=dict(kind='bed', evidence_ref='seen:new_bed')),
                            request=request, obs=observation)
        transport = FixtureTransport([observation.to_dict(), bad, fix,
            {'new_bed': bed()}])
        provider = self.provider(transport)
        self.run_provider(provider, request)
        original = json.loads(transport.bodies[1]['messages'][-1]['content'])
        self.assertEqual(original['required_inventory'], [{'observation_id': 'new_bed', 'category': 'bed'}])
        feedback = json.loads(transport.bodies[2]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(feedback['previous_candidate'], bad)
        self.assertTrue(feedback['validation']['issues'][0]['path'].startswith('$.inventory[0]'))
        self.assertIn('not as an ungrounded text object', transport.bodies[1]['messages'][0]['content'])
        self.assertEqual(original['evidence_catalog'][0]['ref'], 'seen:new_bed')

    def test_observer_repair_preserves_image_once_role_alternation_and_parsed_candidate(self):
        observation = photo_observation('other_bed')
        invalid = {'schema_version': 'bad'}
        transport = FixtureTransport([invalid, observation.to_dict(), bound_visual_structure('other_bed'),
            {'other_bed': bed()}])
        self.run_provider(self.provider(transport), replace(photo_request(), prompt='a bed'))
        messages = transport.bodies[1]['messages']
        self.assertEqual([m['role'] for m in messages], ['system', 'user'])
        parts = messages[-1]['content']
        self.assertEqual(sum(p['type']=='image_url' for p in parts), 1)
        self.assertEqual(json.loads(parts[-1]['text'])['previous_candidate'], invalid)

    def test_partial_coverage_14_to_7_to_1_can_reach_next_stage_with_shared_budget(self):
        from twinpulse_provider import ProviderConfigurationError
        ids = ['seen'+str(i) for i in range(14)]
        observation = photo_observation(*ids)
        request = replace(photo_request(), prompt='a bed')
        # Named slots follow the wire's lexical key order. Each subsequent
        # revision must describe the actual candidate, not a reordered fixture.
        stages = [[], ids[:7], ids[:7]+sorted(ids[7:13]), ids[:7]+sorted(ids[7:13])+ids[13:]]
        candidates = [bound_visual_structure(*identities) for identities in stages]
        fixes = [binding_patch(candidates[index], *[dict(op='add', value=row)
            for row in candidates[index+1]['inventory'][len(candidates[index]['inventory']):]],
            request=request, obs=observation) for index in range(3)]
        transport = FixtureTransport([observation.to_dict(), candidates[0], *fixes,
            ProviderConfigurationError('offline sentinel: reached object parameters')])
        provider = self.provider(transport)
        with self.assertRaisesRegex(ProviderConfigurationError, 'offline sentinel'):
            self.run_provider(provider, request)
        self.assertEqual(provider.diagnostic_for(photo_request().request_id)['stage'], 'objects')
        self.assertEqual(provider._budget.repairs, 3)
        self.assertNotEqual(provider._budget.terminal, 'REPAIR_STALLED')

    def test_public_attempt_list_preserves_policy_ceiling_no_secret_or_candidate(self):
        for count in (4, 10, 32, 35):
            with self.subTest(count=count):
                result = _public_generation_diagnostics({'attempts': [dict(attempt_id=str(i),
                    role='repair', repair=True, candidate='private', request_redacted='private') for i in range(count)]})
                self.assertEqual(len(result['attempts']), min(count, 32))
                self.assertEqual(result['attempts_total'], count)
                self.assertEqual(result['attempts_truncated'], count>32)
                self.assertTrue(all(row['repair'] and row['role']=='repair' for row in result['attempts']))
                self.assertNotIn('private', json.dumps(result))

    def test_actual_audited_worker_persists_requests_validations_and_repair_decisions(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            policy = GenerationPolicy()
            request = text_request()
            rate = dict(input_per_million=1, output_per_million=1, context_tokens=40000, source='offline-fixture')
            scope = OrdinaryInferenceScope('ordinary-generation:repair-evidence', input_digest(request),
                'b'*64, policy.sha256, root/'ledger.json', {PLANNER_MODEL: rate}, '1', 12)
            invalid = {**wire_structure(), 'summary': ''}
            responses = [invalid, binding_patch(invalid, dict(op='summary', value='Estimated bedroom')), {'bed': bed()}]
            wires = []
            class Response:
                def __init__(self, url, raw): self.url, self.raw = url, raw
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def geturl(self): return self.url
                def read(self, *_): return self.raw
            def opener(req, **kwargs):
                body = json.loads(req.data)
                wires.append(body)
                return Response(req.full_url, json.dumps(dict(id=uuid4().hex, model=body['model'],
                    choices=[dict(finish_reason='stop', message=dict(content=json.dumps(responses.pop(0))))],
                    usage=dict(prompt_tokens=10, completion_tokens=20, total_tokens=30))).encode())
            evidence = InferenceEvidence(root/'raw')
            store = ExecutionStore(root/'diagnostics', 'fixture')
            trace = store.begin('generation')
            provider = self.provider(AuditedChatTransport(lambda: 'secret-canary', evidence, opener=opener), route_sha256='b'*64)
            result = self.run_provider(provider, replace(request, inference_scope=scope, diagnostics=trace))
            attempts = result.provider_provenance['budget']['attempts']
            for index, row in enumerate(attempts):
                identity = row['attempt_id']
                dispatch = json.loads((root/'raw'/'dispatches'/f'{identity}.json').read_text())
                self.assertEqual(json.loads(dispatch['request_redacted']), wires[index])
                self.assertEqual(dispatch['request_sha256'], hashlib.sha256(json.dumps(wires[index], sort_keys=True).encode()).hexdigest())
                self.assertEqual(dispatch['stored_request_sha256'], hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest())
                self.assertEqual(dispatch['role'], 'repair' if index==1 else 'initial')
                self.assertTrue((root/'raw'/f'{identity}.json').exists())
                stage = 'objects' if index==2 else 'structure'
                validation = json.loads((root/'raw'/'validations'/f'{identity}-{stage}.json').read_text())
                record = json.loads(validation['record_redacted'])
                self.assertEqual(validation['stored_record_sha256'], hashlib.sha256(validation['record_redacted'].encode()).hexdigest())
                self.assertEqual(record['validation'], 'failed' if index==0 else 'passed')
                self.assertEqual(validation['request_sha256'], dispatch['request_sha256'])
                self.assertEqual(validation['execution_id'], trace.execution_id)
                self.assertEqual(validation['span_id'], dispatch['span_id'])
                if index == 1:
                    self.assertEqual(record['repair_context']['mode'], 'targeted_keyed_changes')
                    self.assertEqual(record['repair_context']['contract_revision'], 'semantic-structure-repair-1.1')
                    self.assertEqual(record['candidate']['changes'], {})
                    self.assertEqual(record['validation_candidate'], {**invalid, 'summary': 'Estimated bedroom'})
            decision = json.loads((root/'raw'/'validations'/f'{attempts[0]["attempt_id"]}-repair_decision.json').read_text())
            self.assertFalse(json.loads(decision['record_redacted'])['progressed'])
            self.assertTrue((root/'raw'/'validations'/f'{attempts[-1]["attempt_id"]}-semantic_compile.json').exists())
            self.assertTrue(all('secret-canary' not in p.read_text() for p in (root/'raw').rglob('*.json')))
            trace.finish('succeeded')
            store.flush()

    def test_local_evidence_redacts_images_secrets_and_preserves_original_files(self):
        with TemporaryDirectory() as folder:
            evidence = InferenceEvidence(Path(folder))
            body = dict(messages=[dict(role='user', content='data:image/png;base64,YWJj')],
                authorization='Bearer my-secret', api_key='my-secret')
            evidence.started('a'*32, {'execution_id': 'execution-fixture'}, request_body=body, secret='my-secret')
            evidence.validation('a'*32, 'structure', {'candidate': body}, secret='my-secret')
            for path in Path(folder).rglob('*.json'):
                raw = path.read_text()
                self.assertNotIn('YWJj', raw)
                self.assertNotIn('my-secret', raw)
                self.assertNotIn('data:image', raw)
            with self.assertRaises(FileExistsError): evidence.validation('a'*32, 'structure', {})

    def test_validation_storage_failure_stops_without_repair_and_keeps_primary_code(self):
        class Broken(FixtureTransport):
            def record_validation(self, *args): raise OSError('fixture storage failure')
        transport = Broken([{**structure(), 'summary': ''}])
        provider = self.provider(transport)
        with self.assertRaises(InvalidProviderResponseError) as caught:
            self.run_provider(provider)
        self.assertEqual(caught.exception.code, 'SEMANTIC_SUMMARY_INVALID')
        self.assertEqual(provider._budget.terminal, 'VALIDATION_EVIDENCE_FAILED')
        self.assertEqual(len(transport.bodies), 1)


if __name__ == '__main__':
    unittest.main()
