# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Host binding/scoped correction regressions. No HTTP, robot or Isaac acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))

from twinpulse_core import canonical_sha256
from twinpulse_provider import GenerationService, InvalidProviderResponseError
from twinpulse_provider.errors import ProviderTimeoutError
from twinpulse_provider.generation_policy import GenerationBudgetError
from twinpulse_provider.nebius_pipeline import ChatCompletion, _json_content
from twinpulse_provider.semantic_bindings import (evidence_catalog, structure_repair_schema,
    structure_repair_context, repair_structure, batch_repair_schema, repair_batch, BINDING_REVISION,
    STRUCTURE_REPAIR_REVISION, replay_legacy_structure_patch)
from twinpulse_provider.semantic_scene import (checked_structure, structure_schema, scene_draft,
    checked_batch, compile_scene, patch_candidate, patch_schema, revision, PATCH_REVISION, _shape_issues)
from twinpulse_provider.stage_transport import (explicit_json_contract, openai_observer_body,
    normalize_json_schema, ConfiguredStageTransport, OPENAI_MINI_SNAPSHOT)
import test_budgeted_generation as fixtures
from test_budgeted_generation import (FixtureTransport, text_request,
    empty_observation, wire_structure, structure, bed, config, PLANNER_MODEL, OBSERVER_MODEL)
from test_scene_contract import observed
from test_photo_layout import request as photo_request


def observation(*identities):
    return observed(*[(identity, 'bed', 'object', 'unknown', .5) for identity in identities])


def bound(*identities):
    value = wire_structure()
    value['inventory'] = [dict(id=identity, kind='bed', evidence_ref='seen:'+identity) for identity in identities]
    return value


def correction(candidate, *operations):
    return dict(base_revision=canonical_sha256(candidate), operations=list(operations))


def diagnosis(candidate, request, obs):
    try:
        checked_structure(candidate, request, obs, bound=True)
    except InvalidProviderResponseError as error:
        return error.contract_report
    raise AssertionError('Expected a failed candidate, not a passing fixture')


def keyed(candidate, request=None, obs=None, *, changes=None, additions=None, room=None, summary=None):
    request, obs = request or text_request(), obs or empty_observation()
    schema = structure_repair_schema(candidate, diagnosis(candidate, request, obs), request, obs)
    value = dict(repair_version=STRUCTURE_REPAIR_REVISION, base_revision=canonical_sha256(candidate),
        changes={key: None for key in schema['properties']['changes']['properties']},
        additions={key: None for key in schema['properties']['additions']['properties']}, room=room, summary=summary)
    value['changes'].update(changes or {})
    value['additions'].update(additions or {})
    return value


class BindingTests(unittest.TestCase):
    def test_catalog_is_request_local_and_excludes_non_objects(self):
        obs = observed(('moving_chair', 'office_chair', 'object', 'unknown', .5),
            ('unknown_cable', 'unknown', 'unknown', 'unknown', .2),
            ('wall', 'wall', 'structure', 'unknown', .5), ('door', 'opening', 'opening', 'unknown', .5),
            ('clear', 'aisle', 'free_space', 'unknown', .5))
        before = obs.to_dict()
        catalog = evidence_catalog(text_request(), obs)
        self.assertEqual([row['ref'] for row in catalog], ['seen:moving_chair', 'seen:unknown_cable', 'text:0', 'hypothesis'])
        self.assertEqual(catalog[1]['source']['basis'], 'inferred')
        catalog[0]['source']['observation_ids'].clear()
        self.assertEqual(obs.to_dict(), before)
        self.assertEqual(evidence_catalog(text_request(), obs)[0]['source']['observation_ids'], ['moving_chair'])

    def test_typed_role_overrides_legacy_robot_kind_without_rewriting_observation(self):
        from types import SimpleNamespace
        entity = dict(id='chair', kind='robot_candidate', role='object', category='office_chair')
        obs = SimpleNamespace(entities=[entity])
        self.assertEqual(evidence_catalog(text_request(), obs)[0]['ref'], 'seen:chair')
        self.assertEqual(entity['kind'], 'robot_candidate')

    def test_exact_text_references_are_host_slices_not_llm_quotes(self):
        prompt = '가구 위치를 추정해 주세요. '*40
        request = text_request(prompt)
        catalog = evidence_catalog(request, empty_observation())
        for row in catalog[:-1]:
            self.assertIn(row['source']['user_quote'], prompt)
            self.assertLessEqual(len(row['source']['user_quote']), 256)
        value = wire_structure()
        result = checked_structure(value, request, empty_observation(), bound=True)
        self.assertEqual(result['inventory'][0]['source'], catalog[0]['source'])
        self.assertEqual(value['inventory'][0]['evidence_ref'], 'text:0')

    def test_source_rewriting_rejected_on_current_wire_legacy_read_is_explicit(self):
        self.assertEqual(checked_structure(structure(), text_request(), empty_observation()), structure())
        with self.assertRaisesRegex(InvalidProviderResponseError, 'BINDING_ITEM_SHAPE_INVALID'):
            checked_structure(structure(), text_request(), empty_observation(), bound=True)

    def test_one_observation_one_object_not_union_of_unrelated_ids(self):
        obs = observation('a', 'b', 'c')
        legacy = structure()
        legacy['inventory'][0]['source'] = dict(basis='visual', observation_ids=['a', 'b', 'c'], user_quote=None)
        with self.assertRaisesRegex(InvalidProviderResponseError, 'SOURCE_MULTI_OBJECT_BINDING'):
            checked_structure(legacy, text_request(), obs)
        value = bound('a', 'b', 'c')
        value['inventory'][1]['evidence_ref'] = 'seen:a'
        with self.assertRaisesRegex(InvalidProviderResponseError, 'BINDING_OBSERVATION_DUPLICATED'):
            checked_structure(value, text_request(), obs, bound=True)

    def test_unknown_or_non_object_ref_cannot_be_invented(self):
        for reference in ('seen:other', 'seen:wall', 'not-a-catalog-ref', ['seen:a']):
            value = bound('a')
            value['inventory'][0]['evidence_ref'] = reference
            with self.subTest(reference=reference), self.assertRaisesRegex(InvalidProviderResponseError, 'BINDING_REFERENCE_INVALID'):
                checked_structure(value, text_request(), observation('a'), bound=True)

    def test_kind_checked_independently_of_valid_reference(self):
        value = bound('a')
        value['inventory'][0]['kind'] = 'wardrobe'
        codes = {row['code'] for row in diagnosis(value, text_request(), observation('a'))['issues']}
        self.assertIn('SOURCE_OBJECT_CATEGORY_MISMATCH', codes)
        self.assertIn('PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING', codes)

    def test_schema_minimum_and_refs_follow_different_inventories(self):
        for ids in ((), ('a',), tuple('p'+str(i) for i in range(17))):
            obs = observation(*ids)
            schema = structure_schema(text_request(), obs, bound=True)
            self.assertEqual(schema['properties']['inventory']['minItems'], len(ids))
            fields = schema['properties']['inventory']['items']['properties']
            self.assertEqual(set(fields), {'id', 'kind', 'evidence_ref'})
            self.assertEqual(fields['evidence_ref']['enum'], ['seen:'+identity for identity in ids]+['text:0', 'hypothesis'])

    def test_hypothesis_marked_unobserved_compiles_but_never_physical(self):
        request, obs = text_request('Create an estimated room'), empty_observation()
        value = wire_structure()
        value['inventory'][0]['evidence_ref'] = 'hypothesis'
        draft = checked_batch({'bed': bed()}, scene_draft(checked_structure(value, request, obs, bound=True)), ['bed'])
        payload, meta = compile_scene(draft, obs, request)
        self.assertEqual(meta['binding_revision'], BINDING_REVISION)
        self.assertEqual(meta['hypotheses'], ['bed'])
        self.assertEqual(meta['hypotheses_status'], 'unobserved_estimates')
        self.assertFalse(meta['physical_authority'])
        self.assertEqual(meta['size_status'], 'estimated_not_measured')
        self.assertEqual(next(row for row in payload['call_evidence'] if row['call_id']=='obj_bed')['basis'], 'inferred')
        fix = dict(patch_version=PATCH_REVISION, base_revision=revision(draft),
            operations=[dict(op='remove', id='bed', reason_code='hypothesis')])
        result = patch_candidate(draft, fix, obs, request=request)
        self.assertEqual(result['inventory'], [])
        self.assertEqual(len(draft['inventory']), 1)
        compile_scene(result, obs, request)

    def test_hypothesis_never_covers_missing_seen_object(self):
        value = wire_structure()
        value['inventory'][0]['evidence_ref'] = 'hypothesis'
        report = diagnosis(value, text_request(), observation('a'))
        self.assertEqual(report['issues'][-1]['missing_ids'], ['a'])

    def test_saved_coverage_counterexample_now_rejected_raw_unchanged(self):
        from scripts.diagnose_model_schema_live import load_original, ORIGINAL, OUT
        paths = [ORIGINAL, OUT/'campaign.json', OUT/'scope.json', OUT/'audit.json']
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        wire, obs, request = load_original()
        value = {'summary': 'Historical coverage counterexample, not a model acceptance.',
            'room': dict(width_m=4, length_m=4, height_m=2.5), 'inventory': [
                dict(id='a', kind='bed', source=dict(basis='visual', observation_ids=['e3', 'e4', 'e5'], user_quote=None)),
                dict(id='b', kind='wardrobe', source=dict(basis='visual', observation_ids=['e6', 'e7', 'e8'], user_quote=None)),
                dict(id='c', kind='cable_bundle', source=dict(basis='visual', observation_ids=['e9', 'e11'], user_quote=None))]}
        self.assertEqual(_shape_issues(value, wire['response_format']['json_schema']['schema']), [])
        with self.assertRaisesRegex(InvalidProviderResponseError, 'SOURCE_MULTI_OBJECT_BINDING'):
            checked_structure(value, request, obs)
        self.assertEqual(before, {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})


class ScopedRepairTests(unittest.TestCase):
    def test_category_and_related_coverage_share_one_slot_real_missing_stays_separate(self):
        request, obs = text_request(), observation('a', 'b', 'c')
        value = bound('a', 'b'); value['inventory'][1]['kind'] = 'desk'
        report = diagnosis(value, request, obs)
        context = structure_repair_context(value, report, request, obs)
        self.assertEqual([row['id'] for row in context['targets']], ['b'])
        self.assertEqual([row['code'] for row in context['targets'][0]['issues']],
            ['SOURCE_OBJECT_CATEGORY_MISMATCH', 'PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING'])
        self.assertEqual([row['ref'] for row in context['missing_observations']], ['seen:c'])
        schema = structure_repair_schema(value, report, request, obs)
        self.assertEqual(list(schema['properties']['additions']['properties']), ['c'])
        fix = keyed(value, request, obs, changes={'b': dict(op='set', value=dict(kind='bed', evidence_ref='seen:b'))},
                    additions={'c': dict(id='new_c', kind='bed', evidence_ref='seen:c')})
        applied = repair_structure(value, fix, report, request, obs)
        checked_structure(applied, request, obs, bound=True)
        self.assertEqual(applied['inventory'][0], value['inventory'][0])

    def test_valid_photo_binding_cannot_be_replaced_by_text_or_a_new_duplicate(self):
        request, obs = text_request(), observation('a')
        value = bound('a'); value['inventory'][0]['kind'] = 'desk'
        report = diagnosis(value, request, obs)
        for fix in (keyed(value, request, obs, changes={'a': dict(op='set',
                        value=dict(kind='bed', evidence_ref='text:0'))}),
                    keyed(value, request, obs, additions={'a': dict(id='extra', kind='bed', evidence_ref='seen:a')})):
            with self.subTest(patch=fix), self.assertRaises(InvalidProviderResponseError) as failure:
                repair_structure(value, fix, report, request, obs)
            self.assertEqual(failure.exception.candidate_value, value)

    def test_kind_and_invalid_reference_can_be_corrected_together(self):
        request, obs = text_request(), observation('a', 'b')
        value = bound('a', 'b'); value['inventory'][1].update(kind='desk', evidence_ref='invented')
        report = diagnosis(value, request, obs)
        fix = keyed(value, request, obs, changes={'b': dict(op='set', value=dict(kind='bed', evidence_ref='seen:b'))})
        applied = repair_structure(value, fix, report, request, obs)
        checked_structure(applied, request, obs, bound=True)
        self.assertEqual(applied['inventory'][0], value['inventory'][0])
        self.assertEqual(value['inventory'][1]['evidence_ref'], 'invented')

    def test_duplicate_binding_is_editable_not_pinned_as_valid_evidence(self):
        request, obs = text_request(), observation('a', 'b')
        value = bound('a', 'b'); value['inventory'][1]['evidence_ref'] = 'seen:a'
        report = diagnosis(value, request, obs)
        self.assertIsNone(structure_repair_context(value, report, request, obs)['targets'][0]['preserved_evidence_ref'])
        applied = repair_structure(value, keyed(value, request, obs, changes={'b': dict(op='set',
            value=dict(kind='bed', evidence_ref='seen:b'))}), report, request, obs)
        checked_structure(applied, request, obs, bound=True)

    def test_conflicting_ids_across_missing_observation_slots_are_atomic(self):
        request, obs = text_request(), observation('a', 'b')
        value = bound(); before = deepcopy(value)
        report = diagnosis(value, request, obs)
        fix = keyed(value, request, obs, additions={i: dict(id='same', kind='bed', evidence_ref='seen:'+i) for i in ('a', 'b')})
        with self.assertRaisesRegex(InvalidProviderResponseError, 'BINDING_REPAIR_DUPLICATE_TARGET') as failure:
            repair_structure(value, fix, report, request, obs)
        self.assertEqual(failure.exception.contract_report['issues'][0]['target_id'], 'same')
        self.assertEqual(failure.exception.candidate_value, before)
        self.assertEqual(value, before)

    def test_no_change_has_exact_error_and_keeps_base(self):
        value = {**wire_structure(), 'summary': ''}
        with self.assertRaisesRegex(InvalidProviderResponseError, 'BINDING_REPAIR_NO_CHANGE') as failure:
            repair_structure(value, keyed(value), diagnosis(value, text_request(), empty_observation()),
                             text_request(), empty_observation())
        self.assertEqual(failure.exception.candidate_value, value)

    def test_legacy_array_not_accepted_as_new_patch_historical_replay_explicit(self):
        request, obs = text_request(), observation('a')
        value = bound('a'); value['inventory'][0]['kind'] = 'desk'
        report = diagnosis(value, request, obs)
        old = correction(value, dict(op='set', id='a', value=dict(kind='bed', evidence_ref='seen:a')),
                         dict(op='set', id='a', value=dict(kind='bed', evidence_ref='text:0')))
        with self.assertRaises(InvalidProviderResponseError):
            repair_structure(value, old, report, request, obs)
        with self.assertRaisesRegex(InvalidProviderResponseError, 'BINDING_REPAIR_DUPLICATE_TARGET'):
            replay_legacy_structure_patch(value, old, report, request, obs)

    def test_actual_saved_failure_context_coalesces_without_altering_history(self):
        from scripts.verify_semantic_scoped_live_recovery import context
        prior = ROOT/'outputs'/'semantic-binding-live-20261009-ten-r2'
        data = context(prior, 'structure')
        # A later explicitly approved settings change is not a mutation by this
        # read-only replay. Seal current external settings for THIS test while
        # keeping every repository historical/raw byte on its original seal.
        current_external={path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in data['protected'] if not Path(path).resolve().is_relative_to(ROOT)}
        request, obs, value = data['request'], data['observation'], data['failed']
        grouped = structure_repair_context(value, data['diagnosis'], request, obs)
        self.assertEqual([target['id'] for target in grouped['targets']], [data['target_id']])
        self.assertEqual(grouped['missing_observations'], [])
        self.assertEqual(len(grouped['targets'][0]['issues']), 2)
        target = grouped['targets'][0]
        applied = repair_structure(value, keyed(value, request, obs, changes={target['id']: dict(op='set',
            value=dict(kind=target['observed_category'], evidence_ref=target['preserved_evidence_ref']))}),
            data['diagnosis'], request, obs)
        checked_structure(applied, request, obs, bound=True)
        self.assertEqual(applied, data['candidates'][1])
        self.assertTrue(all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
            for path,digest in data['protected'].items() if Path(path).resolve().is_relative_to(ROOT)))
        self.assertTrue(all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
            for path,digest in current_external.items()))

    def test_size_and_location_can_change_together_and_again_on_next_revision(self):
        request, obs = text_request(), empty_observation()
        original = checked_batch({'bed': bed()}, scene_draft(checked_structure(wire_structure(), request, obs, bound=True)), ['bed'])
        first_params = {**bed(), 'dimensions_m': [1.2, 1.9, .8], 'region': 'rear_left'}
        first = patch_candidate(original, dict(patch_version=PATCH_REVISION, base_revision=revision(original),
            operations=[dict(op='update', id='bed', value=first_params)]), obs, request=request)
        second_params = {**first_params, 'dimensions_m': [1.1, 1.8, .8], 'region': 'rear_right'}
        second_patch = dict(patch_version=PATCH_REVISION, base_revision=revision(first),
            operations=[dict(op='update', id='bed', value=second_params)])
        second = patch_candidate(first, second_patch, obs, request=request)
        compile_scene(second, obs, request)
        self.assertEqual(second['objects']['bed'], second_params)
        self.assertEqual(original['objects']['bed'], bed())
        with self.assertRaises(InvalidProviderResponseError):
            patch_candidate(original, second_patch, obs, request=request)

    def test_structure_correction_preserves_valid_item_and_original(self):
        request, obs = text_request(), observation('a', 'b')
        value = bound('a', 'b')
        value['inventory'][1]['kind'] = 'wardrobe'
        before = deepcopy(value)
        report = diagnosis(value, request, obs)
        fixed = repair_structure(value, keyed(value, request, obs, changes={'b': dict(op='set',
            value=dict(kind='bed', evidence_ref='seen:b'))}), report, request, obs)
        checked_structure(fixed, request, obs, bound=True)
        self.assertEqual(fixed['inventory'][0], value['inventory'][0])
        self.assertEqual(value, before)
        with self.assertRaises(InvalidProviderResponseError):
            repair_structure(value, keyed(value, request, obs, changes={'a': dict(op='set',
                value=dict(kind='wardrobe', evidence_ref='seen:a'))}), report, request, obs)

    def test_wrong_revision_duplicate_target_and_extra_id_fail_atomically(self):
        value, request, obs = bound('a'), text_request(), observation('a', 'b')
        report = diagnosis(value, request, obs)
        row = dict(id='b', kind='bed', evidence_ref='seen:b')
        good = keyed(value, request, obs, additions={'b': row})
        for patch in ({**good, 'base_revision': '0'*64}, {**good, 'additions': {'b': row, 'c': row}},
                      keyed(value, request, obs, additions={'b': {**row, 'id': 'a'}})):
            before = deepcopy(value)
            with self.subTest(patch=patch), self.assertRaises(InvalidProviderResponseError):
                repair_structure(value, patch, report, request, obs)
            self.assertEqual(before, value)

    def test_invalid_kind_does_not_allow_erasing_its_unique_observation(self):
        value, request, obs = bound('a'), text_request(), observation('a')
        value['inventory'][0]['kind'] = 'wardrobe'
        report = diagnosis(value, request, obs)
        with self.assertRaises(InvalidProviderResponseError):
            repair_structure(value, keyed(value, request, obs, changes={'a': dict(op='remove')}), report, request, obs)

    def test_only_missing_seen_reference_may_be_added(self):
        value, request, obs = bound('a'), text_request(), observation('a', 'b')
        report = diagnosis(value, request, obs)
        wrong = dict(id='new', kind='bed', evidence_ref='hypothesis')
        with self.assertRaises(InvalidProviderResponseError):
            repair_structure(value, keyed(value, request, obs, additions={'b': wrong}), report, request, obs)
        schema = structure_repair_schema(value, report, request, obs)
        self.assertEqual(schema['properties']['additions']['properties']['b']['anyOf'][1]
            ['properties']['evidence_ref']['const'], 'seen:b')

    def test_batch_correction_cannot_overwrite_valid_sibling(self):
        request, obs = text_request(), observation('a', 'b')
        draft = scene_draft(checked_structure(bound('a', 'b'), request, obs, bound=True))
        candidate = {'a': bed(), 'b': {**bed(), 'dimensions_m': [0, 2, .9]}}
        before = deepcopy(candidate)
        good = repair_batch(candidate, correction(candidate, dict(op='set', id='b', value=bed())), draft, ['a', 'b'])
        checked_batch(good, draft, ['a', 'b'])
        self.assertEqual(good['a'], candidate['a'])
        self.assertEqual(candidate, before)
        with self.assertRaises(InvalidProviderResponseError):
            repair_batch(candidate, correction(candidate, dict(op='set', id='a', value=bed())), draft, ['a', 'b'])
        self.assertIn('operations', batch_repair_schema(candidate, draft, ['a', 'b'])['properties'])

    def test_batch_extra_key_discard_and_missing_key_are_scoped(self):
        request, obs = text_request(), empty_observation()
        draft = scene_draft(checked_structure(wire_structure(), request, obs, bound=True))
        candidate = {'not_requested': bed()}
        patch = correction(candidate, dict(op='discard', id='not_requested'), dict(op='set', id='bed', value=bed()))
        self.assertEqual(repair_batch(candidate, patch, draft, ['bed']), {'bed': bed()})

    def test_geometry_add_uses_binding_remove_unique_seen_rejected(self):
        request, obs = text_request('Estimated room'), observation('a')
        draft = checked_batch({'a': bed()}, scene_draft(checked_structure(bound('a'), request, obs, bound=True)), ['a'])
        wrong = dict(patch_version=PATCH_REVISION, base_revision=revision(draft),
            operations=[dict(op='remove', id='a', reason_code='hypothesis')])
        with self.assertRaises(InvalidProviderResponseError):
            patch_candidate(draft, wrong, obs, request=request)
        add = dict(patch_version=PATCH_REVISION, base_revision=revision(draft), operations=[
            dict(op='add', id='estimate', kind='bed', evidence_ref='hypothesis', value={**bed(), 'region': 'rear_right'})])
        result = patch_candidate(draft, add, obs, request=request)
        self.assertEqual(result['inventory'][-1]['source'], dict(basis='inferred', observation_ids=[], user_quote=None))
        self.assertEqual(len(draft['inventory']), 1)
        self.assertIn('evidence_ref', patch_schema(draft, obs, request=request)['properties']['operations']
            ['items']['anyOf'][1]['properties'])

    def test_geometry_patch_cannot_reintroduce_duplicate_seen_binding(self):
        request, obs = text_request(), observation('a')
        draft = checked_batch({'a': bed()}, scene_draft(checked_structure(bound('a'), request, obs, bound=True)), ['a'])
        patch = dict(patch_version=PATCH_REVISION, base_revision=revision(draft), operations=[
            dict(op='add', id='duplicate', kind='bed', evidence_ref='seen:a', value=bed())])
        with self.assertRaisesRegex(InvalidProviderResponseError, 'SEMANTIC_ADD_OBSERVATION_ALREADY_BOUND'):
            patch_candidate(draft, patch, obs, request=request)
        historical = deepcopy(draft)
        historical['inventory'].append({**deepcopy(historical['inventory'][0]), 'id': 'duplicate'})
        historical['objects']['duplicate'] = {**bed(), 'region': 'rear_right'}
        with self.assertRaisesRegex(InvalidProviderResponseError, 'SOURCE_OBSERVATION_DUPLICATED'):
            compile_scene(historical, obs, request)


class WireTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected_at_every_level_not_last_value_wins(self):
        for raw in ('{"a":1,"a":2}', '{"a":1,"a":1}', '{"changes":{"bed":null,"bed":{}}}',
                    '{"items":[{"kind":"bed","kind":"desk"}]}'):
            with self.subTest(raw=raw), self.assertRaises(InvalidProviderResponseError) as failure:
                _json_content(ChatCompletion('fixture', PLANNER_MODEL, raw, 'stop', {}), 'structure')
            self.assertEqual(failure.exception.code, 'PROVIDER_JSON_DUPLICATE_KEY')
            self.assertTrue(failure.exception.duplicate_key)
        self.assertEqual(_json_content(ChatCompletion('fixture', PLANNER_MODEL,
            '{"a":{"kind":"bed"},"b":{"kind":"desk"}}', 'stop', {}), 'structure'),
            {'a': {'kind': 'bed'}, 'b': {'kind': 'desk'}})

    def test_normalization_and_prompt_schema_are_equivalent_idempotent_copy(self):
        schema = structure_schema(text_request(), observation('a'), bound=True)
        original = {'model': PLANNER_MODEL, 'max_tokens': 20000, 'temperature': 0,
            'chat_template_kwargs': {'enable_thinking': False},
            'messages': [dict(role='system', content='Host contract'), dict(role='user', content='{}')],
            'response_format': dict(type='json_schema', json_schema=dict(name='twinpulse_semantic_structure', strict=True, schema=schema))}
        before = deepcopy(original)
        body = explicit_json_contract(original)
        self.assertEqual(original, before)
        self.assertEqual(body, explicit_json_contract(body))
        note = body['messages'][0]['content'].split('\nResponse JSON Schema:\n')[1]
        self.assertEqual(json.loads(note), body['response_format']['json_schema']['schema'])
        self.assertEqual(body['max_tokens'], 20000)
        self.assertEqual(body['chat_template_kwargs'], {'enable_thinking': False})
        sample = bound('a')
        self.assertEqual(_shape_issues(sample, schema), _shape_issues(sample, normalize_json_schema(schema)))
        schema_with_constant = {'type': 'object', 'properties': {'v': {'const': 'same'}}}
        self.assertEqual(normalize_json_schema(schema_with_constant)['properties']['v'], {'enum': ['same'], 'type': 'string'})

    def test_same_schema_for_configured_gpt_and_nvidia_wire_no_image_leak(self):
        class Inner:
            def __init__(self): self.bodies = []
            async def complete(self, body, _token, _config): self.bodies.append(body)
        for provider in ('openai', 'nebius'):
            with self.subTest(provider=provider):
                inner = Inner()
                model = OPENAI_MINI_SNAPSHOT if provider=='openai' else PLANNER_MODEL
                cfg = replace(config(), model_id=model, base_url='https://api.openai.com/v1/' if provider=='openai'
                    else 'https://api.tokenfactory.nebius.com/v1/')
                transport = ConfiguredStageTransport({'observer': inner, 'planner': inner},
                    {'observer': replace(config(), model_id=OBSERVER_MODEL), 'planner': cfg},
                    {'observer': 'nebius', 'planner': provider}, {'observer': 'low', 'planner': 'low'})
                from twinpulse_provider import CancellationToken
                token = CancellationToken()
                body = fixtures.PipelineTests.provider(self, FixtureTransport([])).body('twinpulse_semantic_structure',
                    structure_schema(text_request(), empty_observation(), bound=True), 'Offline', {})
                body['model'] = model
                if provider=='openai': body.pop('chat_template_kwargs')
                asyncio.run(transport.complete(body, token, cfg))
                wire = inner.bodies[0]
                self.assertEqual(wire['messages'][0]['content'].count('Response JSON Schema:'), 1)
                self.assertNotIn('data:image', json.dumps(wire))
                self.assertEqual(wire.get('max_tokens', wire.get('max_completion_tokens')), 20000)
                if provider=='openai': self.assertNotIn('chat_template_kwargs', wire)


class PipelineRepairTests(unittest.TestCase):
    def run_provider(self, responses, request=None):
        class Recording(FixtureTransport):
            def __init__(self, values): super().__init__(values); self.records = []
            def record_validation(self, name, identity, record): self.records.append((name, identity, deepcopy(record)))
        transport = Recording(responses)
        provider = fixtures.PipelineTests.provider(self, transport)
        result = asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2')
            .generate(request or text_request()))
        return result, provider, transport

    def test_same_object_repaired_again_after_validation_against_latest_revision(self):
        obs, request = observation('a', 'b'), replace(photo_request(), prompt='Estimated bedroom')
        raw = bound('a', 'b'); raw['inventory'][1].update(kind='desk', evidence_ref='invalid')
        partial = deepcopy(raw); partial['inventory'][1].update(kind='desk', evidence_ref='seen:b')
        first = keyed(raw, request, obs, changes={'b': dict(op='set', value=dict(kind='desk', evidence_ref='seen:b'))})
        second = keyed(partial, request, obs, changes={'b': dict(op='set', value=dict(kind='bed', evidence_ref='seen:b'))})
        batch = {'a': {**bed(), 'region': 'middle_left'}, 'b': {**bed(), 'region': 'middle_right'}}
        result, _, transport = self.run_provider([obs.to_dict(), raw, first, second, batch], request)
        self.assertEqual(result.provider_provenance['budget']['repairs'], 2)
        self.assertNotEqual(first['base_revision'], second['base_revision'])
        feedback = json.loads(transport.bodies[3]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(feedback['previous_candidate'], partial)
        records = [record for name, _, record in transport.records if name=='structure' and record['role']=='repair']
        self.assertEqual(records[0]['validation_candidate'], partial)
        self.assertEqual(records[1]['validation_candidate'], bound('a', 'b'))
        self.assertTrue(all(r['repair_context']['mode']=='targeted_keyed_changes' for r in records))

    def test_bad_json_patch_preserves_base_and_diagnosis_then_recovers(self):
        value = {**wire_structure(), 'summary': ''}
        fix = keyed(value, summary='Estimated bedroom')
        text = json.dumps(fix)
        ambiguous = ChatCompletion('fixture', PLANNER_MODEL,
            text[:-1]+',"summary":"Conflicting second write"}', 'stop', {})
        result, _, transport = self.run_provider([value, ambiguous, fix, {'bed': bed()}])
        self.assertEqual(result.provider_provenance['budget']['repairs'], 2)
        feedback = json.loads(transport.bodies[2]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(feedback['previous_candidate'], value)
        self.assertEqual(feedback['validation']['issues'][0]['code'], 'SEMANTIC_SUMMARY_INVALID')
        self.assertEqual(feedback['error_code'], 'PROVIDER_JSON_DUPLICATE_KEY')
        self.assertEqual(feedback['failed_patch_validation']['issues'][0]['duplicate_key'], 'summary')
        self.assertEqual(transport.bodies[2]['response_format']['json_schema']['schema']['properties']
            ['base_revision']['enum'], [canonical_sha256(value)])
        failed = next(record for name, _, record in transport.records if name=='structure'
                      and record.get('validation_code')=='PROVIDER_JSON_DUPLICATE_KEY')
        self.assertEqual(failed['validation_candidate'], value)
        self.assertIsNone(failed['candidate'])
        self.assertEqual(failed['repair_base_diagnosis'], feedback['validation'])

    def test_malformed_json_patch_keeps_same_targeted_base_instead_of_replacing_stage(self):
        value = {**wire_structure(), 'summary': ''}
        malformed = ChatCompletion('fixture', PLANNER_MODEL, '{', 'stop', {})
        result, _, transport = self.run_provider([value, malformed, keyed(value, summary='Estimated bedroom'), {'bed': bed()}])
        self.assertEqual(result.provider_provenance['budget']['repairs'], 2)
        feedback = json.loads(transport.bodies[2]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(feedback['previous_candidate'], value)
        self.assertEqual(feedback['error_code'], 'PROVIDER_JSON_INVALID')
        self.assertIn('changes', transport.bodies[2]['response_format']['json_schema']['schema']['properties'])
        self.assertEqual(feedback['failed_patch_validation']['issues'][0]['line'], 1)

    def test_photo_kind_repair_context_groups_coverage_without_text_duplicate(self):
        obs, request = observation('a'), replace(photo_request(), prompt='Create a bed in an estimated room')
        raw = bound('a'); raw['inventory'][0]['kind'] = 'desk'
        fix = keyed(raw, request, obs, changes={'a': dict(op='set', value=dict(kind='bed', evidence_ref='seen:a'))})
        result, _, transport = self.run_provider([obs.to_dict(), raw, fix, {'a': bed()}], request)
        context = json.loads(transport.bodies[2]['messages'][-1]['content'].splitlines()[0])['structure_repair']
        self.assertEqual(context['missing_observations'], [])
        self.assertEqual(len(context['targets']), 1)
        self.assertEqual(len(context['targets'][0]['issues']), 2)
        self.assertEqual(result.provider_provenance['budget']['repairs'], 1)

    def test_scoped_structure_then_batch_partial_repair_uses_latest_candidate(self):
        obs, request = observation('a', 'b'), replace(photo_request(), prompt='Estimated bedroom')
        raw = bound('a', 'b'); raw['inventory'][1]['kind'] = 'wardrobe'
        fix = keyed(raw, request, obs, changes={'b': dict(op='set', value=dict(kind='bed', evidence_ref='seen:b'))})
        batch = {'a': {**bed(), 'region': 'middle_left'}, 'b': {**bed(), 'region': 'middle_right', 'dimensions_m': [0, 2, .9]}}
        batch_fix = correction(batch, dict(op='set', id='b', value={**bed(), 'region': 'middle_right'}))
        result, provider, transport = self.run_provider([obs.to_dict(), raw, fix, batch, batch_fix], request)
        self.assertEqual(result.provider_provenance['budget']['repairs'], 2)
        self.assertEqual(result.provider_provenance['budget']['requests'], 5)
        for name, _, record in transport.records:
            if name in ('structure', 'objects') and record['validation']=='passed' and record['repair_context']:
                self.assertEqual(record['repair_context']['mode'], 'targeted_keyed_changes' if name=='structure'
                                 else 'targeted_operations')
                self.assertIsNotNone(record['validation_candidate'])
                self.assertIn('changes' if name=='structure' else 'operations', record['candidate'])
        ids = {row['attempt_id'] for row in result.provider_provenance['budget']['attempts']}
        self.assertTrue(all(identity in ids for _, identity, _ in transport.records))
        self.assertNotIn('validation_code', provider.diagnostic_for(request.request_id))
        from twinpulse_provider.budgeted_pipeline import LAYOUT_AXIS_INSTRUCTIONS
        batch_bodies=[body for body in transport.bodies
            if body['response_format']['json_schema']['name']=='twinpulse_semantic_batch']
        self.assertEqual(len(batch_bodies),2)
        for body in batch_bodies:
            self.assertIn(LAYOUT_AXIS_INSTRUCTIONS,body['messages'][0]['content'])
        self.assertEqual(list(transport.bodies[2]['response_format']['json_schema']['schema']['properties']
            ['changes']['properties']), ['b'])

    def test_bad_patch_keeps_base_candidate_and_original_diagnosis(self):
        value = {**wire_structure(), 'summary': ''}
        fix = keyed(value, summary='Estimated bedroom')
        wrong = {**fix, 'base_revision': '0'*64}
        result, _, transport = self.run_provider([value, wrong, fix, {'bed': bed()}])
        self.assertEqual(result.provider_provenance['budget']['repairs'], 2)
        feedback = json.loads(transport.bodies[2]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(feedback['previous_candidate'], value)
        self.assertEqual(feedback['validation']['issues'][0]['code'], 'SEMANTIC_SUMMARY_INVALID')
        self.assertIsNotNone(feedback['failed_patch_validation'])
        self.assertEqual(transport.bodies[2]['response_format']['json_schema']['schema']['properties']
            ['base_revision']['enum'], [canonical_sha256(value)])

    def test_malformed_envelope_repairs_only_that_contract_not_validated_stages(self):
        malformed = ChatCompletion('fixture', PLANNER_MODEL, '{', 'stop', {})
        result, _, transport = self.run_provider([malformed, wire_structure(), {'bed': bed()}])
        self.assertEqual(result.provider_provenance['budget']['repairs'], 1)
        self.assertEqual(json.loads(transport.bodies[1]['messages'][-1]['content'].splitlines()[-1])['previous_candidate'], None)
        self.assertIn('inventory', transport.bodies[1]['response_format']['json_schema']['schema']['properties'])

    def test_output_limit_during_repair_stops_without_further_dispatch(self):
        transport = FixtureTransport([{**wire_structure(), 'summary': ''},
            ChatCompletion('length', PLANNER_MODEL, '{', 'length', {'completion_tokens': 20000}), wire_structure()])
        provider = fixtures.PipelineTests.provider(self, transport)
        with self.assertRaises(InvalidProviderResponseError):
            asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
        self.assertEqual(len(transport.bodies), 2)
        self.assertEqual(provider._budget.terminal, 'PROVIDER_OUTPUT_TRUNCATED')

    def test_repeated_invalid_patch_stalls_without_fresh_replacement(self):
        value = {**wire_structure(), 'summary': ''}
        wrong = {**keyed(value, summary='Estimated bedroom'), 'base_revision': '0'*64}
        transport = FixtureTransport([value, wrong, wrong, wire_structure()])
        provider = fixtures.PipelineTests.provider(self, transport)
        with self.assertRaisesRegex(GenerationBudgetError, 'REPAIR_STALLED'):
            asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
        self.assertEqual(len(transport.bodies), 3)
        self.assertTrue(all('changes' in body['response_format']['json_schema']['schema']['properties']
            for body in transport.bodies[1:]))

    def test_unknown_receipt_does_not_start_another_call(self):
        transport = FixtureTransport([ProviderTimeoutError('offline unknown fixture'), wire_structure()])
        provider = fixtures.PipelineTests.provider(self, transport)
        with self.assertRaises(ProviderTimeoutError):
            asyncio.run(GenerationService(provider, config(timeout_s=300), plan_version='2.2').generate(text_request()))
        self.assertEqual(len(transport.bodies), 1)
        self.assertEqual(provider._budget.terminal, 'REMOTE_OUTCOME_UNKNOWN')

    def test_existing_recovery_fixture_matches_current_wire_without_isaac(self):
        from tempfile import TemporaryDirectory
        from scripts.fixture_budgeted_generation import RecoveryFixture
        request = text_request('Create a bed and a desk in an estimated room')
        with TemporaryDirectory() as folder:
            fixture = RecoveryFixture(request, folder, OBSERVER_MODEL, PLANNER_MODEL)
            result = asyncio.run(GenerationService(fixture.provider, config(timeout_s=300), plan_version='2.2').generate(request))
            self.assertEqual(fixture.responses, [])
            self.assertEqual(result.provider_provenance['budget']['requests'], 3)
            self.assertEqual(result.provider_provenance['budget']['repairs'], 1)


if __name__ == '__main__':
    unittest.main()
