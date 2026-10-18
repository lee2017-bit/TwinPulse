# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Zero-network limits/compiler/recovery tests. Not model/Isaac acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))

from twinpulse_core import canonical_sha256
from twinpulse_provider import GenerationRequest, GenerationService, InvalidProviderResponseError, ProviderConfigurationError
from twinpulse_provider.generation_policy import GenerationPolicy, ExecutionBudget, GenerationBudgetError, ProgressTracker
from twinpulse_provider.generation_store import GenerationStore, input_digest
from twinpulse_provider.semantic_scene import (checked_structure, scene_draft, checked_batch,
    compile_scene, apply_patch_candidate, revision, PATCH_REVISION)
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.reliability import CampaignLedger, AuditedChatTransport, InferenceEvidence
from twinpulse_provider.nebius_pipeline import ObservationArtifact, ChatCompletion, parse_chat_completion
from twinpulse_provider.errors import ProviderTimeoutError
from twinpulse_app.generation_scope import OrdinaryInferenceScope
from twinpulse_provider.stage_transport import ConfiguredStageTransport, OPENAI_MINI_SNAPSHOT
from test_nebius_pipeline import config, OBSERVER_MODEL, PLANNER_MODEL


def text_request(prompt='Create a bed in an estimated bedroom', identity='generation-test'):
    return GenerationRequest(identity, prompt)


def empty_observation():
    return ObservationArtifact.from_mapping({'schema_version': '1.0', 'summary': 'No image provided',
        'entities': [], 'relations': [], 'dimensions': [], 'ambiguities': ['unmeasured']})


def structure(width=6, length=6):
    return {'summary': 'Estimated bedroom', 'room': {'width_m': width, 'length_m': length, 'height_m': 2.6},
        'inventory': [{'id': 'bed', 'kind': 'bed', 'source': {
            'basis': 'user', 'observation_ids': [], 'user_quote': 'a bed'}}]}


def wire_structure(width=6, length=6):
    value = structure(width, length)
    value['inventory'] = [dict(id='bed', kind='bed', evidence_ref='text:0')]
    return value


def bed():
    return {'region': 'middle_centre', 'yaw_deg': 0, 'model_id': 'home.bed',
        'dimensions_m': [1.4, 2, .9], 'variant': 'standard', 'finish': 'natural',
        'placement': {'relation': 'floor', 'parent_id': None, 'part': None,
                      'anchor': 'centre', 'elevation_m': None}}


def draft(width=6, length=6):
    request = text_request()
    value = scene_draft(checked_structure(structure(width, length), request, empty_observation()))
    return checked_batch({'bed': bed()}, value, ['bed'])


class Clock:
    now = 0
    def __call__(self): return self.now


class FixtureTransport:
    """Explicit fixture uses the same counter, never an actual endpoint."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.bodies = []

    async def complete(self, body, token, _config):
        budget = token.generation_budget
        identity = budget.reserve(body, role=token.generation_role)
        self.bodies.append(deepcopy(body))
        if body['response_format']['json_schema']['name']=='twinpulse_room_observation':
            value=dict(summary='Explicit fixture coarse room envelope; inventory has not been observed.',ambiguities=['Scale unmeasured'])
        elif body['response_format']['json_schema']['name']=='twinpulse_semantic_room':
            # Explicit seed fixture, derived from the next scripted structure.
            seed=next(row for row in self.responses if isinstance(row,dict) and 'room' in row)
            value={key:deepcopy(seed[key]) for key in ('summary','room')}
        else:
            value = self.responses.pop(0)
        # Offline fixtures retain old host-patch helpers for direct contract
        # tests. Adapt ONLY their scripted wire reply to the new model delta;
        # production does not accept the former operations/request_scope wire.
        schema = body['response_format']['json_schema']['schema']
        if (isinstance(value, dict) and 'operations' in value and
                'changes' in schema.get('properties', {})):
            context = json.loads(body['messages'][-1]['content'].splitlines()[0])
            original = context['candidate']['objects']
            changes = {key: None for key in schema['properties']['changes']['properties']}
            room = None
            valid = True
            for operation in value['operations']:
                if operation['op'] == 'request_scope':
                    continue
                if operation['op'] == 'room':
                    room = operation['value']
                elif operation['op'] == 'update' and operation['id'] in changes:
                    object_id = operation['id']
                    changes[object_id] = {key: deepcopy(item) for key, item in operation['value'].items()
                        if item != original[object_id].get(key)} or None
                elif (operation['op'] == 'update' and
                        operation['value'] == original.get(operation['id'])):
                    continue
                else:
                    valid = False
            if valid:
                value = dict(patch_version='semantic-delta-1.0', base_revision=value['base_revision'],
                    changes=changes, room=room)
        if isinstance(value, Exception):
            budget.settle(identity, status='outcome_unknown' if isinstance(value, ProviderTimeoutError) else 'rejected')
            raise value
        budget.settle(identity, status='received', usage={'prompt_tokens': 5, 'completion_tokens': 10})
        if isinstance(value, ChatCompletion): return replace(value, attempt_id=identity)
        return ChatCompletion(identity, body['model'], json.dumps(value), 'stop',
                              {'prompt_tokens': 5, 'completion_tokens': 10}, attempt_id=identity)


class BudgetTests(unittest.TestCase):
    def test_complete_explicit_policy_and_allocations(self):
        self.assertEqual(GenerationPolicy.from_dict(GenerationPolicy().to_dict()), GenerationPolicy())
        for mutation in ({'total_timeout_s': 300}, {'max_requests': 4}, {'max_repairs': True},
                         {'per_call_timeout_s': 301}, {'schema_version': 'old'}):
            with self.assertRaises(ProviderConfigurationError):
                GenerationPolicy.from_dict({**GenerationPolicy().to_dict(), **mutation})
        with self.assertRaises(ProviderConfigurationError): GenerationPolicy.from_dict({})

    def test_shared_request_reserve_and_thirteenth_zero(self):
        policy = replace(GenerationPolicy(), external_final_review=False)
        budget = ExecutionBudget(policy)
        body = {'model': 'fixture', 'max_tokens': 10}
        for _ in range(11):
            identity = budget.reserve(body)
            budget.settle(identity, status='received')
        with self.assertRaisesRegex(GenerationBudgetError, 'NEEDS_REQUEST_BUDGET'): budget.reserve(body)
        for _ in range(1):
            identity = budget.reserve(body, role='repair')
            budget.settle(identity, status='rejected')
        with self.assertRaisesRegex(GenerationBudgetError, 'REQUEST_LIMIT_REACHED'): budget.reserve(body, role='repair')
        self.assertEqual(len(budget.rows), 12)
        self.assertEqual(budget.repairs, 1)

    def test_final_review_and_one_repair_reserve_still_stop_thirteenth(self):
        budget=ExecutionBudget(replace(GenerationPolicy(),external_final_review=True))
        body={'model':'fixture','max_tokens':10}
        for _ in range(10):
            identity=budget.reserve(body);budget.settle(identity,status='received')
        with self.assertRaisesRegex(GenerationBudgetError,'NEEDS_REQUEST_BUDGET'):budget.reserve(body)
        for role in ('repair','final_review'):
            identity=budget.reserve(body,role=role);budget.settle(identity,status='received')
        with self.assertRaisesRegex(GenerationBudgetError,'REQUEST_LIMIT_REACHED'):budget.reserve(body,role='final_review')
        self.assertEqual(len(budget.rows),12)

    def test_continuation_carries_http_count_and_only_next_repair_slot(self):
        budget=ExecutionBudget(replace(GenerationPolicy(),external_final_review=True))
        budget.carried_requests=8
        body={'model':'fixture','max_tokens':10}
        for _ in range(2):
            identity=budget.reserve(body);budget.settle(identity,status='received')
        with self.assertRaisesRegex(GenerationBudgetError,'NEEDS_REQUEST_BUDGET'):budget.reserve(body)
        for role in ('repair','final_review'):
            identity=budget.reserve(body,role=role);budget.settle(identity,status='received')
        with self.assertRaisesRegex(GenerationBudgetError,'REQUEST_LIMIT_REACHED'):budget.reserve(body,role='repair')
        self.assertEqual(budget.carried_requests+len(budget.rows),12)

    def test_exploration_does_not_claim_progress_or_spend_stall_counter(self):
        budget=ExecutionBudget(GenerationPolicy())
        budget.repair_result(progressed=False,exploratory=True)
        self.assertEqual(budget.no_progress,0)
        budget.repair_result(progressed=False)
        self.assertEqual(budget.no_progress,1)
        with self.assertRaisesRegex(GenerationBudgetError,'REPAIR_STALLED'):budget.repair_result(progressed=False)

    def test_common_repairs_do_not_reset_between_stages(self):
        budget = ExecutionBudget(GenerationPolicy())
        for name in ('observer', 'structure', 'objects'):
            identity = budget.reserve({'model': name, 'max_tokens': 10}, role='repair')
            budget.settle(identity, status='rejected')
        with self.assertRaisesRegex(GenerationBudgetError, 'REPAIR_LIMIT_REACHED'):
            budget.reserve({'model': 'repair', 'max_tokens': 10}, role='repair')

    def test_old_71_plus_19_does_not_dispatch_repair(self):
        clock = Clock()
        policy = replace(GenerationPolicy(), total_timeout_s=90, initial_timeout_s=70,
            repair_timeout_s=10, final_timeout_s=10, repair_start_margin_s=10)
        budget = ExecutionBudget(policy, clock=clock)
        clock.now = 71
        # Only nine seconds are left after the final reserve, not a fresh 300.
        with self.assertRaisesRegex(GenerationBudgetError, 'NEEDS_TIME_BUDGET'):
            budget.reserve({'model': 'fixture', 'max_tokens': 10}, role='repair')
        self.assertFalse(budget.rows)

    def test_unknown_concurrent_and_duplicate_settlement(self):
        budget = ExecutionBudget(GenerationPolicy())
        identity = budget.reserve({'model': 'fixture', 'max_tokens': 10})
        with self.assertRaisesRegex(GenerationBudgetError, 'DISPATCH_IN_FLIGHT'):
            budget.reserve({'model': 'fixture', 'max_tokens': 10})
        budget.settle(identity)
        budget.settle(identity, status='received', usage={'prompt_tokens': 0, 'completion_tokens': 0})
        self.assertEqual(budget.rows[0]['status'], 'outcome_unknown')
        with self.assertRaisesRegex(GenerationBudgetError, 'REMOTE_OUTCOME_UNKNOWN'):
            budget.reserve({'model': 'fixture', 'max_tokens': 10})

    def test_real_financial_algorithm_conservative_unknown_and_cost(self):
        with TemporaryDirectory() as folder:
            rates = {'fixture': {'input_per_million': 1, 'output_per_million': 2,
                                'context_tokens': 100, 'source': 'explicit_test_rate_not_live'}}
            ledger = CampaignLedger(Path(folder)/'ledger.json', approval='ordinary-generation:test',
                rates=rates, limit_usd='.00015', max_requests=12)
            budget = ExecutionBudget(GenerationPolicy(), financial_owner=ledger)
            identity = budget.reserve({'model': 'fixture', 'max_completion_tokens': 10})
            budget.settle(identity)
            self.assertEqual(float(ledger.state['requests'][0]['charged_or_reserved_usd']), .00012)
            next_budget = ExecutionBudget(GenerationPolicy(), financial_owner=ledger)
            with self.assertRaises(ProviderConfigurationError):
                next_budget.reserve({'model': 'fixture', 'max_tokens': 10})
            self.assertFalse(next_budget.rows)

    def test_two_nonprogress_repairs_and_oscillation(self):
        tracker = ProgressTracker()
        first = {'objects': [{'id': 'b'}, {'id': 'a'}], 'summary': 'first'}
        self.assertFalse(tracker.observe(first, ['overlap', 'support']))
        self.assertFalse(tracker.observe({'objects': list(reversed(first['objects'])), 'summary': 'changed'}, ['overlap', 'support']))
        self.assertTrue(tracker.observe({'objects': [{'id': 'a', 'x': 1}]}, ['support']))
        self.assertFalse(tracker.observe(first, ['support']))
        budget = ExecutionBudget(GenerationPolicy())
        budget.repair_result(progressed=False)
        with self.assertRaisesRegex(GenerationBudgetError, 'REPAIR_STALLED'):
            budget.repair_result(progressed=False)

    def test_shared_repair_time_not_three_new_300_second_windows(self):
        clock = Clock()
        budget = ExecutionBudget(GenerationPolicy(), clock=clock)
        identity = budget.reserve({'model': 'fixture', 'max_tokens': 10}, role='repair')
        clock.now = 220
        budget.settle(identity, status='received')
        with self.assertRaisesRegex(GenerationBudgetError, 'NEEDS_TIME_BUDGET'):
            budget.reserve({'model': 'fixture', 'max_tokens': 10}, role='repair')
        self.assertEqual(budget.snapshot()['repair_used_s'], 220)


class SemanticTests(unittest.TestCase):
    def test_compiler_joins_evidence_and_parameter_library(self):
        value = draft()
        before = deepcopy(value)
        plan, receipt = compile_scene(value, empty_observation(), text_request())
        self.assertEqual({c['call_id'] for c in plan['calls']}, {e['call_id'] for e in plan['call_evidence']})
        item = next(c for c in plan['calls'] if c['tool'] == 'place_furniture')
        self.assertEqual(item['arguments']['catalog_version'], 'furniture-parametric-1.0')
        self.assertEqual(item['arguments']['dimensions_m'], [1.4, 2, .9])
        self.assertEqual(receipt['state'], 'APPROXIMATE_TWIN_READY')
        self.assertFalse(receipt['physical_authority'])
        self.assertEqual(value, before)

    def test_ten_by_twelve_is_estimated_not_a_photo_failure(self):
        _, receipt = compile_scene(draft(10, 12), empty_observation(), text_request())
        self.assertEqual(receipt['size_status'], 'estimated_not_measured')

    def test_partial_candidate_cannot_compile_and_cannot_omit(self):
        value = scene_draft(structure())
        with self.assertRaisesRegex(InvalidProviderResponseError, 'SEMANTIC_DRAFT_INCOMPLETE'):
            compile_scene(value, empty_observation(), text_request())
        with self.assertRaisesRegex(InvalidProviderResponseError, 'SEMANTIC_BATCH_IDS_INVALID'):
            checked_batch({}, value, ['bed'])

    def test_invalid_patch_reverts_and_explicit_size_fixed(self):
        value = draft()
        before = deepcopy(value)
        patch = {'patch_version': PATCH_REVISION, 'base_revision': revision(value),
            'operations': [{'op': 'room', 'value': {'width_m': 2, 'length_m': 2, 'height_m': 2.6}}]}
        with self.assertRaises(ValueError): apply_patch_candidate(value, patch, empty_observation(), text_request())
        self.assertEqual(value, before)
        with self.assertRaises(InvalidProviderResponseError):
            apply_patch_candidate(value, {**patch, 'base_revision': 'old'}, empty_observation(), text_request())
        with self.assertRaisesRegex(ValueError, 'PHOTO_LAYOUT_USER_DIMENSIONS_CHANGED'):
            apply_patch_candidate(value, {**patch, 'operations': [{'op': 'room', 'value': {
                'width_m': 8, 'length_m': 8, 'height_m': 2.6}}]}, empty_observation(), text_request('A 6x6m bedroom with a bed'))

    def test_invalid_model_boolean_dimensions_and_parent_not_silently_fixed(self):
        value = scene_draft(structure())
        for field, bad in (('model_id', 'fake.bed'), ('dimensions_m', [True, 2, .9]),
                           ('placement', {'relation': 'surface', 'parent_id': 'absent', 'part': 'body',
                                          'anchor': 'centre', 'elevation_m': None})):
            with self.subTest(field=field), self.assertRaises(InvalidProviderResponseError):
                checked_batch({'bed': {**bed(), field: bad}}, value, ['bed'])

    def test_empty_text_room_is_valid_without_invented_object(self):
        value = scene_draft({**structure(), 'inventory': []})
        payload, _ = compile_scene(value, empty_observation(), text_request('An empty room'))
        self.assertEqual(len(payload['calls']), 1)

    def test_add_is_grounded_and_remove_requires_proven_duplicate(self):
        original = draft()
        desk = {'region': 'rear_right', 'yaw_deg': 0, 'model_id': 'common.desk',
            'dimensions_m': [1.1, .6, .74], 'variant': 'standard', 'finish': 'natural',
            'placement': deepcopy(bed()['placement'])}
        patch = {'patch_version': PATCH_REVISION, 'base_revision': revision(original),
            'operations': [{'op': 'add', 'id': 'desk', 'kind': 'desk',
                'evidence_ref':'text:0', 'value': desk}]}
        result, payload, _ = apply_patch_candidate(original, patch, empty_observation(), text_request('Create a bed and desk'))
        self.assertEqual(len(result['inventory']), 2)
        self.assertEqual(len(original['inventory']), 1)
        self.assertTrue(any(c['arguments'].get('kind') == 'desk' for c in payload['calls']))
        remove = {'patch_version': PATCH_REVISION, 'base_revision': revision(result),
            'operations': [{'op': 'remove', 'id': 'bed', 'duplicate_of': 'desk', 'reason_code': 'duplicate'}]}
        with self.assertRaisesRegex(InvalidProviderResponseError, 'NOT_PROVEN_DUPLICATE'):
            apply_patch_candidate(result, remove, empty_observation(), text_request('Create a bed and desk'))
        observed = ObservationArtifact.from_mapping({'schema_version': '1.0', 'summary': 'Synthetic single bed',
            'entities': [{'id': 'seen', 'kind': 'static_obstacle', 'description': 'bed', 'confidence': .9}],
            'relations': [], 'dimensions': [], 'ambiguities': ['Fixture only']})
        visual = {'basis': 'visual', 'observation_ids': ['seen'], 'user_quote': None}
        duplicate = deepcopy(original)
        duplicate['inventory'] = [dict(id=identity, kind='bed', source=visual) for identity in ('bed', 'duplicate')]
        duplicate['objects']['duplicate'] = deepcopy(bed())
        remove.update(base_revision=revision(duplicate), operations=[{
            'op': 'remove', 'id': 'duplicate', 'duplicate_of': 'bed', 'reason_code': 'duplicate'}])
        result, _, _ = apply_patch_candidate(duplicate, remove, observed, text_request())
        self.assertEqual(list(result['objects']), ['bed'])
        self.assertIn('duplicate', duplicate['objects'])

    def test_reparent_moves_child_and_failed_orphan_reverts(self):
        from twinpulse_core import SiteToolPlan, execute_site_tool_plan
        value = draft()
        value['inventory'] += [{'id': 'desk', 'kind': 'desk', 'source': {
            'basis': 'user', 'observation_ids': [], 'user_quote': 'desk'}}, {'id': 'monitor', 'kind': 'monitor', 'source': {
            'basis': 'user', 'observation_ids': [], 'user_quote': 'monitor'}}]
        value['objects']['desk'] = {**deepcopy(bed()), 'region': 'rear_right', 'model_id': 'common.desk',
            'dimensions_m': [1.1, .6, .74], 'variant': 'standard'}
        value['objects']['monitor'] = {**deepcopy(bed()), 'region': 'rear_right', 'model_id': 'common.monitor',
            'dimensions_m': [.4, .15, .35], 'variant': 'standard', 'finish': 'catalog_default',
            'placement': {'relation': 'surface', 'parent_id': 'desk', 'part': 'top', 'anchor': 'centre', 'elevation_m': None}}
        request = text_request('Create a bed, desk and monitor')
        before, _ = compile_scene(value, empty_observation(), request)
        change = deepcopy(value['objects']['monitor'])
        change['placement'].update(parent_id='bed', part='mattress')
        patch = {'patch_version': PATCH_REVISION, 'base_revision': revision(value),
                 'operations': [{'op': 'update', 'id': 'monitor', 'value': change}]}
        _, after, _ = apply_patch_candidate(value, patch, empty_observation(), request)
        def centre(plan):
            return next(c['arguments']['position_m'] for c in plan['calls'] if c['arguments'].get('id') == 'monitor')
        self.assertNotEqual(centre(before), centre(after))
        self.assertEqual(value['objects']['monitor']['placement']['parent_id'], 'desk')
        change['placement']['parent_id'] = 'missing'
        patch['operations'][0]['value'] = change
        with self.assertRaises(InvalidProviderResponseError): apply_patch_candidate(value, patch, empty_observation(), request)

    def test_store_roundtrip_corruption_and_read_does_not_execute(self):
        with TemporaryDirectory() as folder:
            store = GenerationStore(folder)
            key = 'a'*64
            original = {'state': 'DRAFT_INCOMPLETE', 'draft': draft(), 'automatic_resume': False}
            store.save('checkpoint', key, original)
            self.assertEqual(store.read('checkpoint', key), original)
            path = Path(folder)/'checkpoint'/(key+'.json')
            data = json.loads(path.read_text())
            data['payload']['state'] = 'SIM_READY'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ProviderConfigurationError, 'GENERATION_STORE_CORRUPT'):
                store.read('checkpoint', key)


class PipelineTests(unittest.TestCase):
    def provider(self, transport, **kwargs):
        return BudgetedPipeline(transport, policy=GenerationPolicy(),
            observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version='2.2', planner_template_no_thinking=True,
            stage_output_token_caps={'observer': 4000, 'planner': 20000}, **kwargs)

    def test_text_structure_batch_final_validated_without_image_call(self):
        transport = FixtureTransport([wire_structure(), {'bed': bed()}])
        provider = self.provider(transport)
        result = asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
        self.assertEqual(len(transport.bodies), 2)
        self.assertTrue(all(b['chat_template_kwargs'] == {'enable_thinking': False} for b in transport.bodies))
        self.assertTrue(all(b['max_tokens'] == 20000 for b in transport.bodies))
        self.assertEqual(result.provider_provenance['budget']['requests'], 2)

    def test_failed_room_repaired_by_patch_without_regenerating_inventory(self):
        bad = checked_batch({'bed': bed()}, scene_draft(checked_structure(wire_structure(2, 2),
            text_request(), empty_observation(), bound=True)), ['bed'])
        patch = {'patch_version': PATCH_REVISION, 'base_revision': revision(bad),
            'operations': [{'op': 'room', 'value': {'width_m': 6, 'length_m': 6, 'height_m': 2.6}}]}
        transport = FixtureTransport([wire_structure(2, 2), {'bed': bed()}, patch])
        provider = self.provider(transport)
        result = asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
        self.assertEqual(result.provider_provenance['budget']['repairs'], 1)
        self.assertEqual([b['response_format']['json_schema']['name'] for b in transport.bodies],
            ['twinpulse_semantic_structure', 'twinpulse_semantic_batch', 'twinpulse_semantic_patch'])
        self.assertEqual(transport.bodies[-1]['chat_template_kwargs'], {'enable_thinking': False})

    def test_length_empty_and_partial_both_stop_after_one(self):
        for content in ('', '{"partial":'):
            partial = ChatCompletion('length', PLANNER_MODEL, content, 'length', {'completion_tokens': 20000})
            transport = FixtureTransport([partial, structure()])
            provider = self.provider(transport)
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
            self.assertEqual(len(transport.bodies), 1)
            self.assertEqual(provider._budget.repairs, 0)
            self.assertIn('TRUNCATED', provider._budget.terminal)

    def test_actual_audited_transport_without_approval_does_not_read_key_or_call(self):
        reads = []
        with TemporaryDirectory() as folder:
            audited = AuditedChatTransport(lambda: reads.append(True) or 'canary', InferenceEvidence(Path(folder)),
                opener=lambda *_a, **_kw: self.fail('network forbidden'))
            provider = self.provider(audited)
            with self.assertRaisesRegex(ProviderConfigurationError, 'financial approval'):
                asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
            self.assertFalse(reads)
            self.assertFalse(audited.calls)

    def test_checkpoint_saved_incomplete_on_output_limit_not_sim_ready(self):
        with TemporaryDirectory() as folder:
            transport = FixtureTransport([ChatCompletion('length', PLANNER_MODEL, '', 'length', {})])
            provider = self.provider(transport, store_root=folder)
            request = text_request()
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(request))
            key = canonical_sha256({'request_id': request.request_id, 'input': input_digest(request)})
            record = provider.store.read('checkpoint', key)
            self.assertEqual(record['state'], 'DRAFT_INCOMPLETE')
            self.assertFalse(record['automatic_resume'])
            self.assertEqual(record['Build'], 'NOT_RUN')

    def test_invalid_batch_repair_and_final_patch_share_counter(self):
        bad = checked_batch({'bed': bed()}, scene_draft(checked_structure(wire_structure(2, 2),
            text_request(), empty_observation(), bound=True)), ['bed'])
        patch = {'patch_version': PATCH_REVISION, 'base_revision': revision(bad),
            'operations': [{'op': 'room', 'value': {'width_m': 6, 'length_m': 6, 'height_m': 2.6}}]}
        batch_fix = {'base_revision': canonical_sha256({}),
                     'operations': [{'op': 'set', 'id': 'bed', 'value': bed()}]}
        transport = FixtureTransport([wire_structure(2, 2), {}, batch_fix, patch])
        provider = self.provider(transport)
        result = asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
        self.assertEqual(result.provider_provenance['budget']['repairs'], 2)
        self.assertEqual(result.provider_provenance['budget']['requests'], 4)

    def test_two_failed_patch_updates_stall_and_no_fourth_repair(self):
        bad = checked_batch({'bed': bed()}, scene_draft(checked_structure(wire_structure(2, 2),
            text_request(), empty_observation(), bound=True)), ['bed'])
        same = {'patch_version': PATCH_REVISION, 'base_revision': revision(bad),
                'operations': [{'op': 'update', 'id': 'bed', 'value': bed()}]}
        transport = FixtureTransport([wire_structure(2, 2), {'bed': bed()}, same, same, same])
        provider = self.provider(transport)
        with self.assertRaisesRegex(GenerationBudgetError, 'REPAIR_STALLED'):
            asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
        self.assertEqual(provider._budget.repairs, 2)
        self.assertEqual(len(transport.bodies), 4)

    def test_ordinary_scope_bound_to_input_policy_route_and_not_host_campaign(self):
        with TemporaryDirectory() as folder:
            request = text_request()
            policy = GenerationPolicy()
            scope = OrdinaryInferenceScope('ordinary-generation:explicit-test', input_digest(request), 'b'*64,
                policy.sha256, Path(folder)/'ledger.json', {'fixture': {'input_per_million': 1,
                'output_per_million': 1, 'context_tokens': 100, 'source': 'test-only'}}, '1', 12)
            self.assertEqual(scope.bind(request, policy, 'b'*64).state['requests'], [])
            for r, p, route in ((text_request('changed input'), policy, 'b'*64),
                                 (request, replace(policy, max_requests=13), 'b'*64),
                                 (request, policy, 'c'*64)):
                with self.assertRaisesRegex(ProviderConfigurationError, 'APPROVAL_MISMATCH'):
                    scope.bind(r, p, route)
            with self.assertRaisesRegex(ProviderConfigurationError, 'APPROVAL_MISMATCH'):
                replace(scope, approval_id='old host campaign').bind(request, policy, 'b'*64)

    def test_audited_worker_raw_ids_financial_ids_budget_ids_agree(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            rate = {'input_per_million': 1, 'output_per_million': 1,
                    'context_tokens': 40000, 'source': 'local-fixture-only-not-live-pricing'}
            scope = OrdinaryInferenceScope('ordinary-generation:test-worker', input_digest(text_request()),
                'b'*64, GenerationPolicy().sha256, root/'ledger.json', {PLANNER_MODEL: rate}, '1', 12)
            responses = [wire_structure(), {'bed': bed()}]
            wires = []
            class Response:
                def __init__(self, endpoint, payload): self.endpoint, self.payload = endpoint, payload
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def geturl(self): return self.endpoint
                def read(self, *_): return self.payload
            def opener(req, **kwargs):
                body = json.loads(req.data)
                wires.append((body, kwargs['timeout']))
                return Response(req.full_url, json.dumps({'id': uuid4().hex, 'model': body['model'],
                    'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(responses.pop(0))}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}}).encode())
            audited = AuditedChatTransport(lambda: 'fixture-canary', InferenceEvidence(root/'raw'), opener=opener)
            provider = self.provider(audited, route_sha256='b'*64)
            request = replace(text_request(), inference_scope=scope)
            result = asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(request))
            ledger = json.loads(scope.ledger_path.read_text())
            self.assertEqual({row['attempt_id'] for row in ledger['requests']},
                {row['attempt_id'] for row in result.provider_provenance['budget']['attempts']})
            raw = list((root/'raw').glob('*.json'))
            self.assertEqual({p.stem for p in raw}, {r['attempt_id'] for r in ledger['requests']})
            self.assertTrue(all(0 < timeout <= 300 for _, timeout in wires))
            self.assertTrue(all(body['chat_template_kwargs'] == {'enable_thinking': False} for body, _ in wires))
            self.assertTrue(all('fixture-canary' not in p.read_text() for p in raw))

    def test_configured_transport_uses_remaining_deadline_not_full_route_timeout(self):
        clock = Clock()
        policy = GenerationPolicy()
        budget = ExecutionBudget(policy, clock=clock)
        clock.now = 539
        class Inner:
            async def complete(self, _body, _token, config):
                self.timeout = config.timeout_s
                return None
        inner = Inner()
        configs = {'observer': replace(config(timeout_s=300), model_id=OBSERVER_MODEL),
                   'planner': config(timeout_s=300)}
        transport = ConfiguredStageTransport({'observer': inner, 'planner': inner}, configs,
            {'observer': 'nebius', 'planner': 'nebius'}, {'observer': 'low', 'planner': 'low'})
        from twinpulse_provider import CancellationToken
        token = CancellationToken()
        token.generation_budget = budget
        token.generation_role = 'initial'
        body = PipelineTests.provider(self, FixtureTransport([])).body('twinpulse_semantic_structure',
            {'type': 'object', 'properties': {}}, 'Offline contract', {})
        asyncio.run(transport.complete(body, token, config(timeout_s=300)))
        self.assertEqual(inner.timeout, 1)

    def test_explicit_continuation_skips_completed_structure_preserves_history(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            transport = FixtureTransport([wire_structure(), ChatCompletion('length', PLANNER_MODEL, '', 'length', {})])
            parent_provider = self.provider(transport, store_root=root/'store')
            parent_request = text_request(identity='parent-execution')
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(parent_provider, config(timeout_s=300), plan_version='2.2').generate(parent_request))
            key = canonical_sha256({'request_id': parent_request.request_id, 'input': input_digest(parent_request)})
            parent = parent_provider.store.read('checkpoint', key)
            rate = {'input_per_million': 1, 'output_per_million': 1, 'context_tokens': 40000, 'source': 'fixture-not-live'}
            scope = OrdinaryInferenceScope('ordinary-generation:explicit-continuation', input_digest(parent_request),
                'b'*64, GenerationPolicy().sha256, root/'new-approval-ledger.json', {PLANNER_MODEL: rate},
                '1', 12, approved_checkpoint_sha256=canonical_sha256(parent))
            continued = replace(parent_request, request_id='new-execution', inference_scope=scope, continuation_checkpoint=key)
            next_transport = FixtureTransport([{'bed': bed()}])
            next_provider = self.provider(next_transport, store_root=root/'store', route_sha256='b'*64)
            result = asyncio.run(GenerationService(next_provider, config(timeout_s=300), plan_version='2.2').generate(continued))
            self.assertEqual([b['response_format']['json_schema']['name'] for b in next_transport.bodies], ['twinpulse_semantic_batch'])
            budget = result.provider_provenance['budget']
            self.assertEqual(budget['requests'], 1)
            self.assertEqual(budget['cumulative_requests'], 3)
            self.assertEqual(budget['prior_executions'][0]['stop_reason'], 'PROVIDER_OUTPUT_TRUNCATED')
            self.assertEqual(parent_provider.store.read('checkpoint', key), parent)
            self.assertEqual(len(list((root/'store'/'checkpoint-history'/key).glob('*.json'))), 3)
            with self.assertRaisesRegex(ProviderConfigurationError, 'ALREADY_BOUND'):
                scope.bind(continued, GenerationPolicy(), 'b'*64)

    def test_continuation_unknown_or_wrong_approval_blocks_before_dispatch(self):
        with TemporaryDirectory() as folder:
            provider = self.provider(FixtureTransport([]), store_root=folder)
            request = text_request(identity='continued')
            for parent_budget in ({'in_flight': 'pending', 'attempts': []},
                                  {'in_flight': None, 'attempts': [{'settled': True, 'status': 'outcome_unknown'}]}):
                parent = {'request_id': 'previous', 'approval_id': 'old', 'input_sha256': input_digest(request),
                          'draft': None, 'budget': parent_budget}
                provider.store.save('checkpoint', 'a'*64, parent)
                scope = OrdinaryInferenceScope('ordinary-generation:continuation', input_digest(request), 'b'*64,
                    GenerationPolicy().sha256, Path(folder)/'not-created.json', {}, '1', 12,
                    approved_checkpoint_sha256=canonical_sha256(parent))
                with self.assertRaisesRegex(ProviderConfigurationError, 'REMOTE_OUTCOME_UNKNOWN'):
                    asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(
                        replace(request, inference_scope=scope, continuation_checkpoint='a'*64)))
                self.assertFalse(scope.ledger_path.exists())
            with self.assertRaisesRegex(ProviderConfigurationError, 'REQUIRES_CURRENT_APPROVAL'):
                asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(
                    replace(request, continuation_checkpoint='a'*64)))

    def test_geometry_continuation_preserves_repairs_seen_and_budget(self):
        from test_geometry_repair_loop import fixture,blind,patch
        structure,parameters,draft=fixture()
        with TemporaryDirectory() as folder:
            root=Path(folder);parent_request=text_request(identity='geometry-parent')
            parent_provider=self.provider(FixtureTransport([structure,parameters,
                patch(draft,'shade',blind(2.18)),ChatCompletion('length',PLANNER_MODEL,'','length',{})]),store_root=root/'store')
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(parent_provider,config(timeout_s=300),plan_version='2.2').generate(parent_request))
            key=parent_provider.diagnostic_for(parent_request.request_id)['checkpoint_id']
            parent=parent_provider.store.read('checkpoint',key)
            self.assertEqual(parent['budget']['repairs'],2)
            self.assertGreater(len(parent['geometry_progress']['seen']),1)
            rate={'input_per_million':1,'output_per_million':1,'context_tokens':40000,'source':'fixture-not-live'}
            scope=OrdinaryInferenceScope('ordinary-generation:geometry-resume',input_digest(parent_request),'b'*64,
                GenerationPolicy().sha256,root/'new-ledger.json',{PLANNER_MODEL:rate},'1',12,
                approved_checkpoint_sha256=canonical_sha256(parent))
            continued=replace(parent_request,request_id='geometry-resumed',inference_scope=scope,continuation_checkpoint=key)
            transport=FixtureTransport([patch(parent['draft'],'shade',blind(2.1))])
            provider=self.provider(transport,store_root=root/'store',route_sha256='b'*64)
            result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(continued))
            self.assertEqual(result.provider_provenance['budget']['repairs'],3)
            self.assertEqual(result.provider_provenance['budget']['cumulative_requests'],5)
            state=provider.store.read('checkpoint',result.provider_provenance['checkpoint_id'])
            self.assertGreater(len(state['geometry_progress']['seen']),len(parent['geometry_progress']['seen']))
            self.assertEqual(provider.store.read('checkpoint',key),parent)
            self.assertFalse(result.provider_provenance['physical_authority'])

    def test_old_geometry_checkpoint_without_tracker_blocks_before_paid_binding(self):
        from test_geometry_repair_loop import fixture
        _,_,draft=fixture()
        with TemporaryDirectory() as folder:
            root=Path(folder);request=text_request(identity='old-geometry')
            provider=self.provider(FixtureTransport([]),store_root=root/'store',route_sha256='b'*64)
            parent=dict(request_id='previous',approval_id='old',input_sha256=input_digest(request),draft=draft,
                best_candidate=draft,budget={'in_flight':None,'attempts':[]})
            provider.store.save('checkpoint','a'*64,parent)
            scope=OrdinaryInferenceScope('ordinary-generation:resume-old',input_digest(request),'b'*64,
                GenerationPolicy().sha256,root/'not-created.json',{},'1',12,
                approved_checkpoint_sha256=canonical_sha256(parent))
            with self.assertRaisesRegex(ProviderConfigurationError,'PROGRESS_HISTORY_UNAVAILABLE'):
                asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(
                    replace(request,inference_scope=scope,continuation_checkpoint='a'*64)))
            self.assertFalse(scope.ledger_path.exists())

    def test_external_review_missing_approval_engine_rejected_before_any_dispatch(self):
        provider = BudgetedPipeline(FixtureTransport([]), policy=replace(GenerationPolicy(), external_final_review=True),
            observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL, site_plan_version='2.2')
        from twinpulse_provider import ImageInput
        request=replace(text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),))
        with self.assertRaisesRegex(ProviderConfigurationError,'REQUIRES_APPROVAL_AND_ENGINE'):
            asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(provider._transport.bodies,[])

    def test_real_diagnostics_span_connected_to_generation(self):
        from twinpulse_core.execution_diagnostics import ExecutionStore
        with TemporaryDirectory() as folder:
            trace = ExecutionStore(Path(folder), 'diagnostic-fixture').begin('scene_generation')
            provider = self.provider(FixtureTransport([wire_structure(), {'bed': bed()}]))
            result = asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(
                replace(text_request(), diagnostics=trace)))
            trace.finish('succeeded')
            trace.store.flush()
            self.assertEqual(result.provider_provenance['budget']['requests'], 2)

    def test_observation_cache_reused_for_planner_change_not_observer_change(self):
        from twinpulse_provider import ImageInput
        with TemporaryDirectory() as folder:
            root = Path(folder)
            image_request = replace(text_request('Create an empty estimated room'),
                images=(ImageInput('fixture.png', 'image/png', b'explicit fixture bytes'),))
            empty = {**structure(), 'inventory': []}
            rate = {'input_per_million': 1, 'output_per_million': 1, 'context_tokens': 40000, 'source': 'fixture-not-live'}
            def run(identity, route, wire, responses):
                scope = OrdinaryInferenceScope('ordinary-generation:'+identity, input_digest(image_request), route,
                    GenerationPolicy().sha256, root/(identity+'.json'), {OBSERVER_MODEL: rate, PLANNER_MODEL: rate}, '1', 12)
                transport = FixtureTransport(responses)
                provider = self.provider(transport, store_root=root/'store', route_sha256=route, observer_wire_policy=wire)
                result = asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(
                    replace(image_request, request_id=identity, inference_scope=scope)))
                return provider, transport, result
            observer = {**empty_observation().to_dict(), 'schema_version':'1.5'}
            first, t1, _ = run('first', 'b'*64, {'origin': 'same'}, [observer, empty])
            second, t2, result = run('planner-change', 'c'*64, {'origin': 'same'}, [empty])
            self.assertEqual(len(t1.bodies), 2)
            self.assertEqual(len(t2.bodies), 1)
            self.assertTrue(second.diagnostic_for('planner-change')['observation_cache_hit'])
            self.assertEqual(result.provider_provenance['budget']['requests'], 1)
            _, t3, _ = run('observer-change', 'c'*64, {'origin': 'changed'}, [observer, empty])
            self.assertEqual(len(t3.bodies), 2)
            self.assertNotIn('data:image', json.dumps(t2.bodies[0]))

    def test_cancelled_audited_worker_settles_late_without_next_dispatch(self):
        from threading import Event
        from twinpulse_provider.errors import GenerationCancelledError
        with TemporaryDirectory() as folder:
            root = Path(folder)
            entered, release = Event(), Event()
            rate = {'input_per_million': 1, 'output_per_million': 1, 'context_tokens': 40000, 'source': 'fixture-not-live'}
            scope = OrdinaryInferenceScope('ordinary-generation:late-worker', input_digest(text_request()), 'b'*64,
                GenerationPolicy().sha256, root/'ledger.json', {PLANNER_MODEL: rate}, '1', 12)
            class Response:
                def __init__(self, endpoint, payload): self.endpoint, self.payload = endpoint, payload
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def geturl(self): return self.endpoint
                def read(self, *_): return self.payload
            wires = []
            def opener(req, **kwargs):
                body = json.loads(req.data)
                wires.append(body)
                entered.set()
                if not release.wait(2): raise TimeoutError('fixture release timeout')
                return Response(req.full_url, json.dumps({'id': 'late', 'model': body['model'],
                    'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(wire_structure())}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 20}}).encode())
            provider = self.provider(AuditedChatTransport(lambda: 'fixture-canary', InferenceEvidence(root/'raw'), opener=opener),
                                     route_sha256='b'*64)
            service = GenerationService(provider, config(timeout_s=300), plan_version='2.2')
            async def scenario():
                task = asyncio.create_task(service.generate(replace(text_request(), inference_scope=scope)))
                for _ in range(200):
                    if entered.is_set(): break
                    await asyncio.sleep(.005)
                self.assertTrue(entered.is_set())
                service.cancel_active()
                release.set()
                with self.assertRaises(GenerationCancelledError): await task
            try: asyncio.run(scenario())
            finally: release.set()
            self.assertEqual(len(wires), 1)
            ledger = json.loads(scope.ledger_path.read_text())
            self.assertEqual(len(ledger['requests']), 1)
            # The HTTP body arrived, but cancellation rejects applying it.
            # Usage is still settled; "received" is not a scene-success claim.
            self.assertEqual(ledger['requests'][0]['status'], 'rejected')
            self.assertEqual(ledger['requests'][0]['usage']['completion_tokens'], 20)
            self.assertEqual(provider._budget.terminal, 'GENERATION_CANCELLED')
            self.assertFalse(scope.ledger_path.with_suffix('.dispatch-lock').exists())


if __name__ == '__main__': unittest.main()
