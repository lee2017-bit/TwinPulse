# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic inventory work, checkpoint retention and explicit bounded continuation."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import test_budgeted_generation as f
from test_observation_instances import grouped
from twinpulse_provider import GenerationService, ImageInput
from twinpulse_provider.generation_policy import GenerationPolicy, GenerationBudgetError
from twinpulse_provider.generation_store import input_digest
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.observation_instances import expand_observation_instances
from twinpulse_app.generation_scope import OrdinaryInferenceScope
from twinpulse_core import canonical_sha256


def many_objects(count=60):
    raw=grouped(count)
    observation,_=expand_observation_instances(ObservationArtifact.from_mapping(raw))
    structure=dict(summary='Explicit synthetic inventory; dimensions estimated',
        room=dict(width_m=12,length_m=12,height_m=2.6),inventory=[dict(
            id='seat_'+str(i),kind='chair',evidence_ref='seen:'+row['id'])
            for i,row in enumerate(observation.entities)])
    item=dict(region='middle_centre',yaw_deg=0,model_id='common.chair',dimensions_m=[.4,.4,.9],
        variant='standard',finish='natural',placement=dict(relation='floor',parent_id=None,
            part=None,anchor='centre',elevation_m=None))
    batches=[{row['id']:deepcopy(item) for row in structure['inventory'][start:start+6]}
        for start in range(0,count,6)]
    return raw,structure,batches


class InventoryWorkTests(unittest.TestCase):
    def test_only_pending_initial_http_soft_stop_can_extend(self):
        from twinpulse_provider.budgeted_pipeline import pending_initial_allowance_extended
        policy=GenerationPolicy();new=replace(policy,max_requests=24)
        parent=dict(policy=policy.to_dict(),budget=dict(stop_reason='NEEDS_REQUEST_BUDGET',
            max_requests=12,cumulative_requests=11,repairs=0),stop_stage='objects',
            stop_role='initial',initial_closed=False,pending_parameter_ids=['seat_59'],stage_route_sha256='same')
        self.assertTrue(pending_initial_allowance_extended(parent,new,'same'))
        for patch in (dict(stop_stage='repair'),dict(stop_role='repair'),dict(initial_closed=True),
                dict(pending_parameter_ids=[]),dict(stage_route_sha256='changed'),
                dict(budget=parent['budget']|dict(stop_reason='REQUEST_LIMIT_REACHED')),
                dict(budget=parent['budget']|dict(cumulative_requests=12))):
            self.assertFalse(pending_initial_allowance_extended(parent|patch,new,'same'))
        self.assertFalse(pending_initial_allowance_extended(parent,policy,'same'))
        self.assertFalse(pending_initial_allowance_extended(parent,replace(new,max_repairs=4),'same'))
        self.assertFalse(pending_initial_allowance_extended(parent,replace(new,external_final_review=True),'same'))

    def provider(self,transport,**kwargs):
        policy=kwargs.pop('policy',GenerationPolicy())
        return f.BudgetedPipeline(transport,policy=policy,observer_model_id=f.OBSERVER_MODEL,
            planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2',planner_template_no_thinking=True,
            stage_output_token_caps={'observer':4000,'planner':20000},**kwargs)

    def test_large_inventory_finishes_through_normal_compiler_without_count_loss(self):
        raw,structure,batches=many_objects()
        policy=replace(GenerationPolicy(),max_requests=24,external_final_review=False)
        transport=f.FixtureTransport([raw,structure,*batches])
        request=replace(f.text_request('Estimate the observed objects'),images=(ImageInput('fixture.jpg','image/jpeg',b'offline-only'),))
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,policy=policy,store_root=folder)
            result=asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(len(cp['draft']['inventory']),60)
        self.assertEqual(len(cp['draft']['objects']),60)
        self.assertEqual(cp['pending_parameter_ids'],[])
        self.assertTrue(cp['inventory_progress']['parameters_complete'])
        self.assertTrue(result.provider_provenance['checks_complete'])
        self.assertEqual(len([r for r in result.plan.to_dict()['calls'] if r['tool']=='place_furniture']),60)
        self.assertGreater(len(result.plan.to_dict()['calls']),40)
        from twinpulse_core import execute_site_tool_plan
        self.assertGreater(len(execute_site_tool_plan(result.plan,source='photo',source_ref='a'*64).scene.objects),64)
        self.assertEqual(len(transport.bodies),12)
        self.assertFalse(cp['physical_authority'])

    def test_budget_stop_keeps_all_inventory_and_continues_only_pending_batches(self):
        raw,structure,batches=many_objects()
        request=replace(f.text_request('Estimate the observed objects',identity='inventory-parent'),
            images=(ImageInput('fixture.jpg','image/jpeg',b'offline-only'),))
        with TemporaryDirectory() as folder:
            root=Path(folder)
            first=f.FixtureTransport([raw,structure,*batches])
            provider=self.provider(first,store_root=root/'store')
            with self.assertRaises(GenerationBudgetError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            key=provider.diagnostic_for(request.request_id)['checkpoint_id']
            parent=provider.store.read('checkpoint',key)
            self.assertEqual(len(parent['draft']['inventory']),60)
            # Only the next repair slot is reserved, not all three optional
            # repairs: eleven initial HTTP now complete nine object batches.
            self.assertEqual(len(parent['draft']['objects']),54)
            self.assertEqual(len(parent['pending_parameter_ids']),6)
            self.assertEqual(parent['source_observation'],raw)
            self.assertEqual(parent['Run'],'NOT_RUN')
            self.assertIsNone(parent['compiled_plan'])
            self.assertTrue(parent['inventory_progress']['checkpoint_saved'])
            self.assertFalse(parent['inventory_progress']['parameters_complete'])
            saved=deepcopy(parent)
            # A NEW explicit approval raises cumulative request allowance;
            # prior time, requests, repairs and costs are carried, never erased.
            policy=replace(GenerationPolicy(),max_requests=24,external_final_review=False)
            rate=dict(input_per_million=1,output_per_million=1,context_tokens=40000,source='fixture-not-live')
            scope=OrdinaryInferenceScope('ordinary-generation:inventory-resume',input_digest(request),'b'*64,
                policy.sha256,root/'new-ledger.json',{f.PLANNER_MODEL:rate},'1',24,
                approved_checkpoint_sha256=canonical_sha256(parent))
            transport=f.FixtureTransport(batches[9:])
            resumed=self.provider(transport,store_root=root/'store',policy=policy,route_sha256='b'*64)
            result=asyncio.run(GenerationService(resumed,f.config(timeout_s=300),plan_version='2.2').generate(
                replace(request,request_id='inventory-resumed',inference_scope=scope,continuation_checkpoint=key)))
            final=resumed.store.read('checkpoint',resumed.diagnostic_for('inventory-resumed')['checkpoint_id'])
            self.assertEqual(provider.store.read('checkpoint',key),saved)
            self.assertEqual(len(transport.bodies),1)
            self.assertEqual(final['draft']['objects']|parent['draft']['objects'],final['draft']['objects'])
            self.assertEqual(final['inventory_progress']['pending_count'],0)
            self.assertEqual(result.provider_provenance['budget']['cumulative_requests'],12)

    def test_public_progress_is_safe_and_never_grants_completion_or_motion(self):
        from twinpulse_app.product_workflow_service import _public_generation_diagnostics
        progress=dict(schema_version='inventory-work-progress-1.0',observed_instances=60,
            inventory_count=60,parameterized_count=42,pending_count=18,parameter_batch_size=6,
            inventory_planned=True,parameters_complete=False,checkpoint_saved=True,
            automatic_resume=True,physical_authority=True,private_text='not public')
        public=_public_generation_diagnostics({'inventory_progress':progress})['inventory_progress']
        self.assertFalse(public['automatic_resume']);self.assertFalse(public['physical_authority'])
        self.assertNotIn('private_text',public)
        for mutation in ({'pending_count':0},{'parameterized_count':True},{'parameters_complete':True}):
            self.assertNotIn('inventory_progress',_public_generation_diagnostics({'inventory_progress':progress|mutation}))

    def test_expansion_resource_stop_preserves_compressed_source_without_erasing_count(self):
        from twinpulse_provider import ProviderConfigurationError
        raw=grouped(10**9)
        transport=f.FixtureTransport([raw])
        request=replace(f.text_request('Estimate the observed group'),images=(ImageInput('fixture.jpg','image/jpeg',b'offline-only'),))
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,store_root=folder)
            with self.assertRaisesRegex(ProviderConfigurationError,'EXPANSION_MEMORY_BUDGET'):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(cp['source_observation'],raw)
        self.assertEqual(cp['observation'],raw)
        self.assertIsNone(cp['draft']);self.assertIsNone(cp['compiled_plan'])
        self.assertEqual(cp['inventory_progress']['pending_count'],10**9)
        self.assertTrue(cp['inventory_progress']['checkpoint_saved'])
        self.assertFalse(cp['inventory_progress']['inventory_planned'])
        self.assertEqual(cp['budget']['repairs'],0);self.assertEqual(len(transport.bodies),1)
        self.assertEqual(cp['Run'],'NOT_RUN')

    def test_large_valid_scene_still_obeys_geometry_memory_and_duplicate_identity_guards(self):
        from twinpulse_core import execute_site_tool_plan
        from twinpulse_core.validation import ValidationLimits,validate_scene_geometry,SpecValidationError
        from twinpulse_core.scene_resources import check_scene_payload
        from twinpulse_core import SiteToolPlan
        payload,_=f.compile_scene(f.draft(),f.empty_observation(),f.text_request())
        plan=execute_site_tool_plan(SiteToolPlan.from_dict(payload),source='manual',source_ref='a'*64)
        with self.assertRaisesRegex(SpecValidationError,'memory budget'):
            validate_scene_geometry(plan.scene.id,plan.scene.objects,ValidationLimits(max_objects=None,max_scene_bytes=1))
        with self.assertRaisesRegex(SpecValidationError,'unique'):
            validate_scene_geometry(plan.scene.id,(plan.scene.objects[0],plan.scene.objects[0]),ValidationLimits(max_objects=None))
        with self.assertRaisesRegex(ValueError,'MEMORY_BUDGET'):
            check_scene_payload({'oversized':'x'*(2*1024*1024)})
