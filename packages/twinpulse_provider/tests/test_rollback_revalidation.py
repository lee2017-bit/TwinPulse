# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Zero-network rollback regression; not fresh model or Isaac acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch as mock_patch

from test_scope_quality_loop import photo_case, patch
from test_budgeted_generation import FixtureTransport, config, OBSERVER_MODEL, PLANNER_MODEL, empty_observation, text_request
from twinpulse_provider import GenerationService
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy, GenerationBudgetError
from twinpulse_provider.semantic_scene import patch_candidate, revision, checked_structure, checked_batch, scene_draft, compile_scene


class RollbackRevalidationTests(unittest.TestCase):
    def run_case(self, policy, repeated=False, recover=False):
        request, obs, structure, objects, candidate = photo_case()
        structure['room'].update(width_m=3.2, length_m=3.2)
        candidate = checked_batch(objects, scene_draft(checked_structure(
            structure, request, obs, bound=True)), list(objects))
        invalid = dict(objects['bed'], region='rear_left')
        bad = patch(candidate, [dict(op='update', id='bed', value=invalid)])
        broken = patch_candidate(candidate, bad, obs, request)
        responses = [obs.to_dict(), structure, objects, bad]
        if repeated:
            second_bad = dict(objects['desk'], dimensions_m=[1.2, .6, 3 if recover else .74])
            second_patch = patch(broken, [dict(op='update', id='desk', value=second_bad)])
            responses.append(second_patch)
            if recover:
                second_candidate = patch_candidate(broken, second_patch, obs, request)
                # Return to the earlier failed A revision (A -> B -> A), not
                # a no-change patch rejected before the compiler runs.
                responses.append(patch(second_candidate, [
                    dict(op='update', id='desk', value=objects['desk'])]))
        if recover:
            responses.append(patch(candidate, [
                dict(op='update', id='bed', value=dict(objects['bed'], region='rear_left')),
                dict(op='update', id='desk', value=dict(objects['desk'], region='rear_right'))]))
        transport = FixtureTransport(responses)
        with TemporaryDirectory() as folder:
            provider = BudgetedPipeline(transport, policy=policy, store_root=folder,
                observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
                site_plan_version='2.2', planner_template_no_thinking=True)
            result = error = None
            try:
                result = asyncio.run(GenerationService(provider, config(timeout_s=300),
                    plan_version='2.2').generate(request))
            except Exception as caught:
                error = caught
            diagnostic = provider.diagnostic_for(request.request_id)
            state = provider.store.read('checkpoint', diagnostic['checkpoint_id'])
        return result, error, diagnostic, state, transport, candidate

    def test_last_slot_rolls_back_revalidates_and_stops_for_quality_not_unmapped(self):
        result, error, diag, state, transport, candidate = self.run_case(
            replace(GenerationPolicy(), max_repairs=1))
        self.assertIsNone(result)
        self.assertIsInstance(error, GenerationBudgetError)
        self.assertEqual(error.code, 'QUALITY_REPAIR_LIMIT_REACHED')
        self.assertEqual(len(transport.bodies), 4)
        self.assertEqual(state['budget']['repairs'], 1)
        self.assertEqual(revision(state['draft']), revision(candidate))
        self.assertIsNone(state['compiled_plan'])
        self.assertEqual(state['rollback_revalidation']['validation'], 'passed')
        self.assertEqual(state['rollback_revalidation']['quality_status'], 'needs_revision')
        self.assertTrue(state['rollback_revalidation']['failed_diagnosis']['issues'])
        self.assertEqual(state['patches'][0]['validation'], 'failed')
        self.assertNotEqual(state['patches'][0].get('geometry_validation'), 'passed')
        self.assertEqual(diag['stage_acceptance']['photo_quality'], 'needs_revision')

    def test_geometry_regressions_return_to_quality_and_can_recover(self):
        result, error, diag, state, transport, candidate = self.run_case(
            replace(GenerationPolicy(), max_repairs=4, stalled_repairs=4), repeated=True, recover=True)
        self.assertIsNone(error, str(error))
        self.assertIsNotNone(result)
        self.assertEqual(len(transport.bodies), 7)
        self.assertEqual(state['budget']['repairs'], 4)
        self.assertEqual(state['budget']['stalled_repairs'], 0)
        self.assertEqual(state['state'], 'APPROXIMATE_TWIN_READY')
        self.assertEqual([p['validation'] for p in state['patches']], ['failed', 'failed', 'failed', 'passed'])
        content = json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertEqual(content['repair_kind'], 'quality')
        self.assertEqual(revision(content['candidate']), revision(candidate))
        self.assertTrue(content['validation']['issues'])
        self.assertEqual(state['rollback_revalidation']['external_call'], False)

    def test_stall_keeps_failed_branch_and_rechecked_best_without_more_dispatch(self):
        result, error, diag, state, transport, candidate = self.run_case(
            GenerationPolicy(), repeated=True)
        self.assertIsNone(result)
        self.assertIsInstance(error, GenerationBudgetError)
        self.assertEqual(error.code, 'REPAIR_STALLED')
        self.assertEqual(len(transport.bodies), 5)
        self.assertEqual(state['budget']['repairs'], 2)
        self.assertEqual(state['budget']['stalled_repairs'], 2)
        self.assertEqual(revision(state['draft']), revision(candidate))
        self.assertIsNone(state['compiled_plan'])
        self.assertTrue(state['working_branch']['diagnosis']['issues'])
        self.assertEqual(state['rollback_revalidation']['candidate_revision'], revision(candidate))
        self.assertEqual(state['rollback_revalidation']['validation'], 'passed')
        self.assertEqual(state['rollback_revalidation']['quality_status'], 'needs_revision')
        self.assertEqual(diag['stage_acceptance']['approximate_draft'], 'blocked')

    def test_public_rollback_separates_failed_cause_from_restored_checks(self):
        from twinpulse_app.product_workflow_service import _public_generation_diagnostics
        _, _, diag, state, _, candidate = self.run_case(GenerationPolicy(), repeated=True)
        public = _public_generation_diagnostics(diag)['rollback_revalidation']
        self.assertEqual(public['validation'], 'passed')
        self.assertEqual(public['quality_status'], 'needs_revision')
        self.assertEqual(public['failed_codes'], ['PHOTO_LAYOUT_REGION_FULL'])
        self.assertEqual(public['candidate_revision'], revision(candidate))
        self.assertFalse(public['external_call'])
        self.assertNotIn('failed_diagnosis', public)
        self.assertNotIn('objects', public)
        unsafe = deepcopy(state['rollback_revalidation'])
        unsafe.update(candidate_revision='not-a-hash', external_call=True)
        unsafe['failed_diagnosis']['issues'].append(dict(code='secret prose'))
        filtered = _public_generation_diagnostics(dict(rollback_revalidation=unsafe))['rollback_revalidation']
        self.assertNotIn('candidate_revision', filtered)
        self.assertEqual(filtered['failed_codes'], ['PHOTO_LAYOUT_REGION_FULL'])
        self.assertFalse(filtered['external_call'])
        unsafe['failed_diagnosis'] = None
        self.assertEqual(_public_generation_diagnostics(dict(rollback_revalidation=unsafe))[
            'rollback_revalidation']['failed_codes'], [])

    def test_restored_candidate_is_rechecked_not_trusted_when_checker_fails(self):
        initial = None
        def changed_checker(draft, observation, request, **options):
            nonlocal initial
            if initial is None:
                initial = revision(draft)
            elif revision(draft) == initial:
                raise ValueError('INTERNAL_CHECKER_FAILURE')
            return compile_scene(draft, observation, request, **options)
        with mock_patch('twinpulse_provider.budgeted_pipeline.compile_scene', side_effect=changed_checker):
            result, error, diag, state, transport, candidate = self.run_case(
                replace(GenerationPolicy(), max_repairs=1))
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertEqual(len(transport.bodies), 4)
        self.assertEqual(state['rollback_revalidation']['validation'], 'failed')
        self.assertEqual(state['rollback_revalidation']['quality_status'], 'not_run')
        self.assertIsNone(state['compiled_plan'])
        self.assertNotEqual(diag['stage_acceptance']['approximate_draft'], 'passed')
        self.assertEqual(error.code, 'ROLLBACK_REVALIDATION_FAILED')

    def test_previously_failing_geometry_revision_remains_repairable(self):
        request = text_request('Create an estimated room with a bed and desk')
        obs = empty_observation()
        _, _, structure, objects, _ = photo_case()
        structure['room'].update(width_m=3.2, length_m=3.2)
        structure['inventory'] = [dict(id=i, kind=k, evidence_ref='text:0')
            for i, k in [('bed','bed'), ('desk','desk')]]
        objects['bed']['region'] = 'rear_left'
        original = checked_batch(objects, scene_draft(checked_structure(
            structure, request, obs, bound=True)), list(objects))
        worse = dict(objects['desk'], dimensions_m=[1.1, .6, 3])
        first = patch(original, [dict(op='update', id='desk', value=worse)])
        bad = patch_candidate(original, first, obs, request)
        transport = FixtureTransport([structure, objects, first,
            patch(bad, [dict(op='update', id='desk', value=objects['desk'])]),
            patch(original, [dict(op='update', id='desk', value=dict(objects['desk'], region='rear_right'))])])
        with TemporaryDirectory() as folder:
            provider = BudgetedPipeline(transport, policy=replace(GenerationPolicy(), stalled_repairs=3),
                store_root=folder, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
                site_plan_version='2.2')
            result = asyncio.run(GenerationService(provider, config(timeout_s=300),
                plan_version='2.2').generate(request))
            saved = provider.store.read('checkpoint', provider.diagnostic_for(request.request_id)['checkpoint_id'])
        # Returning to the original still-failing revision is not a success
        # and need not abandon the branch: its fresh error remains repairable.
        self.assertIsNone(saved['rollback_revalidation'])
        last = json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertEqual(last['repair_kind'], 'geometry')
        self.assertEqual(revision(last['candidate']), revision(original))
        self.assertEqual(last['validation']['issues'][0]['code'], 'PHOTO_LAYOUT_REGION_FULL')
        self.assertEqual(result.provider_provenance['budget']['repairs'], 3)
        self.assertTrue(result.provider_provenance['checks_complete'])

    def test_restored_geometry_still_requires_new_current_render_review(self):
        import test_render_review_loop as rendered
        request, port, obs, structure, objects, _ = rendered.case()
        structure['room'].update(width_m=3.2, length_m=3.2)
        candidate = checked_batch(objects, scene_draft(checked_structure(
            structure, request, obs, bound=True)), list(objects))
        bad = patch(candidate, [dict(op='update', id='bed', value=dict(objects['bed'], region='rear_left'))])
        transport = rendered.DynamicFixtureTransport([obs.to_dict(), structure, objects,
            lambda b: rendered.review_response(b, contradiction=True), bad,
            lambda b: rendered.review_response(b)])
        with TemporaryDirectory() as folder:
            provider = BudgetedPipeline(transport,
                policy=replace(GenerationPolicy(), external_final_review=True, max_repairs=1),
                store_root=folder, observer_model_id=OBSERVER_MODEL,
                planner_model_id=PLANNER_MODEL, site_plan_version='2.2')
            result = asyncio.run(GenerationService(provider, config(timeout_s=300),
                plan_version='2.2').generate(request))
            saved = provider.store.read('checkpoint', provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(len(port.captures), 2)
        self.assertNotEqual(port.captures[0]['metadata']['frame_id'], port.captures[1]['metadata']['frame_id'])
        self.assertEqual([r['status'] for r in saved['render_history']], ['needs_revision', 'consistent'])
        self.assertEqual(saved['render_capture'], saved['render_history'][-1]['capture'])
        self.assertEqual(saved['patches'][0]['validation'], 'failed')
        self.assertNotEqual(saved['patches'][0].get('geometry_validation'), 'passed')
        self.assertEqual(result.provider_provenance['quality_review']['candidate_revision'], revision(candidate))
        self.assertEqual(result.provider_provenance['budget']['repairs'], 1)


if __name__ == '__main__':
    unittest.main()
