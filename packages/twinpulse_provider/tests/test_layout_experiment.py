# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline search contracts, not new model/Isaac or photo-quality evidence."""
import asyncio
from copy import deepcopy
import unittest
from tempfile import TemporaryDirectory

import test_render_review_loop as fixtures
from twinpulse_provider import GenerationService, InvalidProviderResponseError
from twinpulse_provider.layout_experiment import objective, response_schema, checked_response, compile_result, repair_strategy
from twinpulse_provider.repair_scope import delta_schema
from twinpulse_provider.render_review import checked, body
from twinpulse_provider.semantic_scene import compile_scene, revision
from twinpulse_provider.scene_contract import SceneContractError


def sample():
    request, port, obs, _, _, draft = fixtures.pending_case()
    plan, _ = compile_scene(draft, obs, request, progressive=True)
    capture = asyncio.run(port.capture(plan, revision(draft), None, 300));capture['plan'] = plan
    wire = body(request, draft, obs, capture, model='fixture', cap=4000)
    response = fixtures.review_response(wire)
    response['objects']['bed']['layout'].update(status='contradiction', confidence=.55)
    diagnosis = checked(response, draft, plan, capture, dict(issues=[
        dict(code='PHOTO_PENDING_SUPPORT_NEEDS_REVISION', target_ids=['bed'])]))
    return draft, plan, diagnosis


class LayoutExperimentTests(unittest.TestCase):
    def test_current_major_layout_conflicts_precede_support_capability(self):
        draft, plan, diagnosis = sample()
        for code in ('RENDER_LAYOUT_MISMATCH', 'PHOTO_RELATIVE_ORDER_CONTRADICTION',
                     'PHOTO_OBSERVED_REGION_CONTRADICTION'):
            mixed = deepcopy(diagnosis)
            mixed['issues'].append(dict(code=code, target_ids=['bed']))
            before = deepcopy(mixed)
            decision = repair_strategy(draft, mixed, plan, [])
            self.assertEqual(decision['strategy'], 'semantic_layout')
            self.assertEqual(decision['reason_codes'], [code])
            self.assertFalse(decision['extra_call_authority'])
            self.assertEqual(mixed, before)  # pending evidence is not discarded
            stale = deepcopy(mixed);stale['candidate_revision'] = '0'*64
            self.assertEqual(repair_strategy(draft, stale, plan, [])['strategy'], 'capability_first')
            self.assertEqual(repair_strategy(draft, mixed, dict(calls=[]), [])['strategy'], 'capability_first')

    def test_untried_layout_objective_precedes_capability_without_repeating_it(self):
        draft, plan, diagnosis = sample()
        self.assertEqual(repair_strategy(draft, diagnosis, plan, [])['strategy'], 'focused_layout')
        focus = objective(draft, diagnosis, plan, [])
        self.assertEqual(repair_strategy(draft, diagnosis, plan, [focus])['strategy'], 'capability_first')
        no_hypothesis = deepcopy(diagnosis)
        no_hypothesis['assessments']['bed']['layout'].update(status='consistent', confidence=.9)
        self.assertEqual(repair_strategy(draft, no_hypothesis, plan, [])['strategy'], 'capability_first')

    def test_pipeline_with_eligible_library_capability_dispatches_semantic_first(self):
        # Explicit offline transport only: this proves routing, not photo quality.
        from dataclasses import replace
        from twinpulse_provider.model_capability_repair import capability_diagnosis, capability_targets
        class Library:
            def snapshots(self):return {}
            def register(self, *args, **kwargs):raise AssertionError('No recipe creation expected')
        request, port, obs, structure, objects, draft = fixtures.pending_case()
        request = replace(request, model_library_port=Library())
        plan, checks = compile_scene(draft, obs, request, progressive=True)
        capture = asyncio.run(port.capture(plan, revision(draft), None, 300));capture['plan'] = plan
        wire = body(request, draft, obs, capture, model='fixture', cap=4000)
        diagnosis = checked(fixtures.review_response(wire, contradiction=True), draft, plan, capture,
            dict(issues=[dict(code='PHOTO_PENDING_SUPPORT_NEEDS_REVISION', target_ids=['bed'])]))
        targets = capability_targets(draft,
            capability_diagnosis(diagnosis, checks['progressive_twin']), obs)
        self.assertIn('bed', targets)  # Not the old model_library_port=None early return.
        port.captures.clear()
        def semantic(wire):
            self.assertEqual(wire['response_format']['json_schema']['name'], 'twinpulse_semantic_patch')
            props = wire['response_format']['json_schema']['schema']['properties']
            constant = lambda key: props[key].get('const', (props[key].get('enum') or [None])[0])
            return dict(patch_version=constant('patch_version'), base_revision=constant('base_revision'),
                room=None, changes={identity:dict(region='front_right') if identity=='bed' else None
                    for identity in props['changes']['properties']})
        models = {identity:value['model_id'] for identity,value in objects.items()
                  if value['placement']['relation']=='floor'}
        transport = fixtures.DynamicFixtureTransport([obs.to_dict(), structure, models, objects,
            lambda wire:fixtures.review_response(wire, contradiction=True), semantic, fixtures.review_response])
        pipeline = fixtures.provider(transport)
        pipeline.policy = replace(pipeline.policy, max_repairs=1)
        result = asyncio.run(GenerationService(pipeline, fixtures.fixtures.config(timeout_s=300),
            plan_version='2.2').generate(request))
        self.assertEqual(len(transport.bodies), 7)
        self.assertEqual(pipeline._budget.repairs, 1)
        self.assertEqual(pipeline._diagnostic['quality_repair_strategy']['strategy'], 'semantic_layout')
        self.assertEqual(result.provider_provenance['progressive_twin']['unresolved'][0]['id'], 'cover')
        self.assertEqual(len(port.captures), 2)

    def test_bound_untried_floor_root_not_reused_or_used_for_hard_failure(self):
        draft, plan, diagnosis = sample()
        focus = objective(draft, diagnosis, plan, [])
        self.assertEqual(focus['target_id'], 'bed');self.assertFalse(focus['verified'])
        self.assertIsNone(objective(draft, diagnosis, plan, [dict(layout_experiment=focus)]))
        self.assertIsNone(objective(draft, diagnosis, plan, [focus]))
        hard = deepcopy(diagnosis);hard['issues'].append(dict(code='RENDER_LAYOUT_MISMATCH', target_ids=['bed']))
        self.assertIsNone(objective(draft, hard, plan, []))
        stale = deepcopy(diagnosis);stale['capture']['plan_sha256'] = '0'*64
        self.assertIsNone(objective(draft, stale, plan, []))
        wrong = deepcopy(plan);wrong['calls'] = []
        self.assertIsNone(objective(draft, diagnosis, wrong, []))

    def test_prop_only_changes_cannot_claim_root_trial(self):
        draft, plan, diagnosis = sample();focus = objective(draft, diagnosis, plan, [])
        schema = delta_schema(draft, diagnosis)
        raw = dict(patch_version='semantic-delta-1.0', base_revision=revision(draft), room=None,
            changes={i: None for i in schema['properties']['changes']['properties']},
            layout_experiment=dict(target_id='bed', outcome='trial', reason='Synthetic trial'))
        after = deepcopy(draft);after['objects']['cover']['region'] = 'front_left'
        with self.assertRaisesRegex(SceneContractError, 'INTENT_MISMATCH'):
            checked_response(raw, schema, focus, draft, after)
        raw['layout_experiment']['outcome'] = 'abstain'
        record = checked_response(raw, schema, focus, draft, after)
        self.assertFalse(record['root_parameters_changed']);self.assertFalse(record['verified'])
        after['objects']['bed']['yaw_deg'] = 90
        raw['layout_experiment']['outcome'] = 'trial'
        record = checked_response(raw, schema, focus, draft, after)
        unchanged = compile_result(record, plan)
        self.assertEqual(unchanged['compiled_effect'], 'unchanged_or_not_rendered')
        changed_plan = deepcopy(plan)
        next(c for c in changed_plan['calls'] if c['arguments']['id']=='bed')['arguments']['yaw_deg'] = 90
        result = compile_result(record, changed_plan)
        self.assertEqual(result['compiled_effect'], 'changed_not_quality_proof')
        self.assertEqual(result['quality_outcome'], 'fresh_current_review_required')
        self.assertFalse(result['verified'])

    def test_missing_or_fabricated_focus_contract_is_rejected(self):
        draft, plan, diagnosis = sample();focus = objective(draft, diagnosis, plan, [])
        schema = delta_schema(draft, diagnosis)
        self.assertIn('layout_experiment', response_schema(schema, focus)['required'])
        self.assertNotIn('layout_experiment', schema['required'])
        for raw in ([], {}, dict(layout_experiment=None)):
            with self.assertRaises(SceneContractError):checked_response(raw, schema, focus, draft, draft)

    def test_hard_support_overlap_does_not_unlock_root_dimensions_or_room(self):
        draft, plan, diagnosis = sample();focus = objective(draft, diagnosis, plan, [])
        schema=delta_schema(draft,diagnosis)
        wire=response_schema(schema,focus)
        self.assertEqual(set(wire['properties']['changes']['properties']['bed']['anyOf'][1]['properties']),
            {'region','yaw_deg','placement'})
        self.assertEqual(wire['properties']['room'],{'type':'null'})
        raw=dict(patch_version='semantic-delta-1.0',base_revision=revision(draft),room=None,
            changes={i:None for i in schema['properties']['changes']['properties']},
            layout_experiment=dict(target_id='bed',outcome='abstain',reason='No source-supported trial'))
        for mode in ('dimensions','model','room'):
            after=deepcopy(draft)
            if mode=='dimensions':after['objects']['bed']['dimensions_m'][0]+=.1
            elif mode=='model':after['objects']['bed']['model_id']='common.desk'
            else:after['room']['width_m']-=.1
            with self.assertRaisesRegex(SceneContractError,'SCOPE_VIOLATION'):
                checked_response(raw,schema,focus,draft,after)

    def test_no_change_abstention_does_not_spend_another_call(self):
        request, port, obs, structure, objects, draft = fixtures.pending_case()
        def low(body):
            response = fixtures.review_response(body)
            response['objects']['bed']['layout'].update(status='contradiction', confidence=.55)
            return response
        def abstain(body):
            schema = body['response_format']['json_schema']['schema']['properties']
            constant = lambda k: schema[k].get('const', (schema[k].get('enum') or [None])[0])
            return dict(patch_version=constant('patch_version'), base_revision=constant('base_revision'),
                room=None, changes={i: None for i in schema['changes']['properties']},
                layout_experiment=dict(target_id='bed', outcome='abstain', reason='Unclear synthetic view'))
        transport = fixtures.DynamicFixtureTransport([obs.to_dict(), structure, objects, low, abstain])
        with TemporaryDirectory() as root:
            pipeline = fixtures.provider(transport,store_root=root)
            with self.assertRaisesRegex(InvalidProviderResponseError, 'SEMANTIC_PATCH_NO_CHANGE'):
                asyncio.run(GenerationService(pipeline, fixtures.fixtures.config(timeout_s=300), plan_version='2.2').generate(request))
            diag=pipeline.diagnostic_for(request.request_id)
            saved=pipeline.store.read('checkpoint',diag['checkpoint_id'])
            event=saved['layout_experiments'][0]
            self.assertTrue(event['no_op']);self.assertFalse(event['verified'])
            self.assertEqual(event['intent']['outcome'],'abstain')
            self.assertEqual(saved['patches'],[])
            self.assertIsNone(objective(saved['draft'],saved['quality_review'],saved['compiled_plan'],
                saved['layout_experiments']))
        self.assertEqual(len(transport.bodies), 5)
        self.assertEqual(pipeline._budget.repairs, 1)
        self.assertEqual(len(port.captures), 1)

    def test_final_validated_quality_abstention_retains_only_current_checked_partial(self):
        from dataclasses import replace
        request, port, obs, structure, objects, draft = fixtures.pending_case()
        def low(body):
            response=fixtures.review_response(body)
            response['objects']['bed']['layout'].update(status='contradiction',confidence=.55)
            return response
        def abstain(body):
            props=body['response_format']['json_schema']['schema']['properties']
            constant=lambda k:props[k].get('const',(props[k].get('enum') or [None])[0])
            return dict(patch_version=constant('patch_version'),base_revision=constant('base_revision'),
                room=None,changes={i:None for i in props['changes']['properties']},
                layout_experiment=dict(target_id='bed',outcome='abstain',reason='Unclear synthetic view'))
        for stale in (False,True):
            with self.subTest(stale=stale):
                port.stale=False;port.captures.clear()
                def final_abstain(body):
                    port.stale=stale
                    return abstain(body)
                transport=fixtures.DynamicFixtureTransport([obs.to_dict(),structure,objects,low,final_abstain])
                pipeline=fixtures.provider(transport)
                pipeline.policy=replace(pipeline.policy,max_repairs=1)
                service=GenerationService(pipeline,fixtures.fixtures.config(timeout_s=300),plan_version='2.2')
                if stale:
                    from twinpulse_provider import ProviderConfigurationError
                    with self.assertRaisesRegex(ProviderConfigurationError,'RENDER_REVIEW_SUPERSEDED'):
                        asyncio.run(service.generate(request))
                    self.assertNotIn('draft_refinement',pipeline._diagnostic)
                else:
                    result=asyncio.run(service.generate(request))
                    provenance=result.provider_provenance
                    self.assertEqual(provenance['draft_refinement']['stop_reason'],'QUALITY_REPAIR_LIMIT_REACHED')
                    self.assertEqual(provenance['quality_review']['status'],'needs_revision')
                    self.assertEqual([r['id'] for r in provenance['progressive_twin']['unresolved']],['cover'])
                    self.assertEqual(pipeline._diagnostic['repair_terminal_cause']['validation_code'],
                        'SEMANTIC_PATCH_NO_CHANGE')
                    self.assertFalse(pipeline._diagnostic['repair_terminal_cause']['patch_applied'])
                    self.assertEqual(pipeline._diagnostic['attempts'][-1]['patch_effect'],'no_change')
                    self.assertEqual(pipeline._diagnostic['attempts'][-1]['validation'],'failed')
                    self.assertFalse(pipeline._diagnostic['layout_experiments'][0]['verified'])
                self.assertEqual(len(transport.bodies),5)
                self.assertEqual(len(port.captures),1)
                self.assertEqual(pipeline._budget.repairs,1)


if __name__ == '__main__':unittest.main()
