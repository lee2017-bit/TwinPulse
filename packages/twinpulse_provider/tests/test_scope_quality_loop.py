# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Zero-network product scope/quality repair; not rendered image fidelity."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
import test_budgeted_generation as fixtures
from test_budgeted_generation import FixtureTransport,bed,text_request,empty_observation,config
from twinpulse_provider import GenerationService,ImageInput,InvalidProviderResponseError
from twinpulse_provider.semantic_scene import (checked_structure,checked_batch,scene_draft,revision,
    patch_candidate,PATCH_REVISION,compile_scene,review_candidate_quality)
from twinpulse_provider.repair_scope import checked_scope,scope_options
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.generation_policy import GenerationBudgetError
from twinpulse_provider.observation_alignment import unknown_alignment


def desk(region='rear_left'):
    return dict(region=region,yaw_deg=0,model_id='common.desk',dimensions_m=[1.1,.6,.74],
        variant='standard',finish='natural',placement=dict(relation='floor',parent_id=None,
            part=None,anchor='centre',elevation_m=None))


def photo_case():
    request=replace(text_request('Make an estimated room from this photo'),
        images=(ImageInput('synthetic.jpg','image/jpeg',b'explicit-offline-fixture'),))
    observation=ObservationArtifact.from_mapping(dict(schema_version='1.5',summary='Synthetic unknown scale',
        entities=[dict(id=i,kind='static_obstacle',description=k,confidence=.9,
            role='object',category=k,region='unknown',spatial_confidence=.9,instance_count=1,
            footprint_alignment=unknown_alignment()) for i,k in
            (('seen_bed','bed'),('seen_desk','desk'))],
        relations=[dict(subject_id='seen_bed',relation='left_of',object_id='seen_desk')],
        dimensions=[],ambiguities=['Unmeasured']))
    structure=dict(summary='Estimated room',room=dict(width_m=6,length_m=6,height_m=2.6),
        inventory=[dict(id=i,kind=k,evidence_ref='seen:'+o) for i,k,o in
            (('bed','bed','seen_bed'),('desk','desk','seen_desk'))])
    objects={'bed':dict(bed(),region='rear_right'),'desk':desk()}
    candidate=checked_batch(objects,scene_draft(checked_structure(structure,request,observation,bound=True)),list(objects))
    return request,observation,structure,objects,candidate


def patch(candidate,operations):
    return dict(patch_version=PATCH_REVISION,base_revision=revision(candidate),operations=operations)


class ScopeQualityTests(unittest.TestCase):
    def provider(self,transport,**kwargs):return fixtures.PipelineTests.provider(self,transport,**kwargs)

    def test_camera_region_is_an_unverified_projection_not_a_paid_world_position_repair(self):
        request=replace(text_request('Create this unmeasured space'),
            images=(ImageInput('fixture.jpg','image/jpeg',b'offline-only'),))
        obs=ObservationArtifact.from_mapping(dict(schema_version='1.5',summary='Synthetic support case',
            entities=[dict(id=i,kind='static_obstacle',description=k,confidence=.9,role='object',
                category=k,region=r,spatial_confidence=.9,instance_count=1,
                footprint_alignment=unknown_alignment()) for i,k,r in
                [('support_seen','desk','unknown'),('item_seen','tabletop_item','rear_right')]],
            relations=[],dimensions=[],ambiguities=['No measured coordinates']))
        structure=dict(summary='Estimated support case',room=dict(width_m=6,length_m=6,height_m=2.6),
            inventory=[dict(id=i,kind=k,evidence_ref='seen:'+ref) for i,k,ref in
                [('support','desk','support_seen'),('item','tabletop_item','item_seen')]])
        objects=dict(support=desk(),item=dict(region='rear_right',yaw_deg=0,
            model_id='common.tabletop_item',dimensions_m=[.2,.2,.1],variant='standard',
            finish='catalog_default',placement=dict(relation='surface',parent_id='support',
                part='top',anchor='centre',elevation_m=None)))
        candidate=checked_batch(objects,scene_draft(checked_structure(structure,request,obs,bound=True)),list(objects))
        def review(value):
            payload,provenance=compile_scene(value,obs,request)
            return review_candidate_quality(value,payload,provenance,obs,request)
        initial=review(candidate)
        self.assertEqual(initial['issues'],[]);self.assertEqual(initial['status'],'uncertain')
        problem=initial['observed_photo_relations']['region_checks'][0]
        self.assertGreater(problem['violation_m'],0)
        self.assertLess(problem['estimated_position_m'][0],0)
        self.assertEqual(problem['status'],'UNVERIFIED_REGION_PROJECTION')
        self.assertFalse(problem['metric_error_valid']);self.assertTrue(problem['hypothesis_disagrees'])
        # A child region edit alone does not move an attached item.
        declaration_only=deepcopy(candidate);declaration_only['objects']['item']['region']='middle_right'
        self.assertEqual(review(declaration_only)['observed_photo_relations']['region_checks'][0]['violation_m'],problem['violation_m'])
        smaller=deepcopy(candidate);smaller['room']['width_m']=5
        reduced=review(smaller)
        self.assertLess(reduced['observed_photo_relations']['region_checks'][0]['violation_m'],problem['violation_m'])
        self.assertEqual(reduced['issues'],[]);self.assertEqual(reduced['status'],'uncertain')
        transport=FixtureTransport([obs.to_dict(),structure,objects])
        provider=self.provider(transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(result.provider_provenance['budget']['repairs'],0)
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(result.provider_provenance['quality_review']['status'],'uncertain')

    def test_quality_conflict_feeds_typed_patch_and_full_compile_in_same_budget(self):
        request,observation,structure,objects,candidate=photo_case(); original=deepcopy(candidate)
        operations=[dict(op='update',id='bed',value=dict(objects['bed'],region='rear_left')),
            dict(op='update',id='desk',value=dict(objects['desk'],region='rear_right'))]
        transport=FixtureTransport([observation.to_dict(),structure,objects,patch(candidate,operations)])
        with TemporaryDirectory() as root:
            provider=self.provider(transport,store_root=root)
            result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
            diag=provider.diagnostic_for(request.request_id)
            saved=provider.store.read('checkpoint',diag['checkpoint_id'])
            self.assertEqual(saved['quality_progress']['history'][0]['decision'],'initial')
            self.assertEqual(revision(saved['quality_best']),revision(saved['draft']))
            self.assertEqual(saved['quality_progress']['history'][-1]['decision'],'progress')
        content=json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertEqual(content['repair_kind'],'quality')
        self.assertEqual(result.provider_provenance['budget']['repairs'],1)
        self.assertEqual(result.provider_provenance['budget']['requests'],4)
        self.assertTrue(result.provider_provenance['checks_complete'])
        self.assertEqual(result.provider_provenance['patches'][0]['repair_kind'],'quality')
        self.assertEqual(result.provider_provenance['quality_review']['status'],'uncertain')
        self.assertEqual(result.provider_provenance['quality_review']['render_comparison'],'not_run')
        self.assertFalse(result.provider_provenance['quality_review']['issues'])
        self.assertEqual(candidate,original)

    def test_repeated_quality_conflict_retains_partial_without_promoting_photo_quality(self):
        request,observation,structure,objects,candidate=photo_case()
        changed=dict(objects['bed'],dimensions_m=[1.3,2,.9])
        middle=patch_candidate(candidate,patch(candidate,[dict(op='update',id='bed',value=changed)]),observation,request)
        changed2=dict(changed,dimensions_m=[1.2,2,.9])
        transport=FixtureTransport([observation.to_dict(),structure,objects,
            patch(candidate,[dict(op='update',id='bed',value=changed)]),
            patch(middle,[dict(op='update',id='bed',value=changed2)])])
        provider=self.provider(transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        diag=provider.diagnostic_for(request.request_id)
        self.assertEqual(diag['budget']['repairs'],2)
        self.assertEqual(diag['stage_acceptance']['approximate_draft'],'partial')
        self.assertEqual(diag['stage_acceptance']['photo_quality'],'needs_revision')
        self.assertEqual(result.provider_provenance['draft_refinement']['stop_reason'],'REPAIR_STALLED')
        self.assertEqual(len(transport.bodies),5)

    def test_low_confidence_relation_does_not_force_a_guess_or_paid_repair(self):
        request,obs,structure,objects,_=photo_case(); raw=obs.to_dict()
        for e in raw['entities']:e['spatial_confidence']=.4
        transport=FixtureTransport([raw,structure,objects]);provider=self.provider(transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(result.provider_provenance['budget']['repairs'],0)
        self.assertEqual(result.provider_provenance['quality_review']['status'],'uncertain')

    def scope_case(self):
        request,obs,structure,objects,candidate=photo_case()
        # Pure host diagnostic: one crowded estimated floor cell. No photo ID
        # or fixture values appear in production eligibility checks.
        diag={'issues':[dict(code='PHOTO_LAYOUT_REGION_FULL',target_ids=['desk'])]}
        candidate['objects']['bed']['region']='middle_left'
        return request,obs,candidate,diag

    def test_host_accepts_neighbor_scope_and_atomic_update_without_extra_call(self):
        request,obs,candidate,diag=self.scope_case(); original=deepcopy(candidate)
        context,options=scope_options(candidate,diag)
        self.assertEqual([i['id'] for i in context['targets']],['desk'])
        self.assertIn(dict(id='bed',anchor_id='desk',reason_code='packing_neighbor',
            evidence='same_or_adjacent_estimated_packing_region'),options)
        operations=[dict(op='request_scope',id='bed',anchor_id='desk',reason_code='packing_neighbor'),
            dict(op='update',id='bed',value=dict(candidate['objects']['bed'],region='middle_right'))]
        result=patch_candidate(candidate,patch(candidate,operations),obs,request,repair_diagnosis=diag)
        decision=checked_scope(candidate,patch(candidate,operations),diag)
        self.assertIn('bed',decision['allowed_ids']);self.assertEqual(len(decision['accepted']),1)
        self.assertNotEqual(revision(result),revision(candidate));self.assertEqual(candidate,original)

    def test_arbitrary_outside_update_scope_text_and_stale_base_are_rejected(self):
        request,obs,candidate,diag=self.scope_case()
        change=dict(op='update',id='bed',value=dict(candidate['objects']['bed'],region='middle_right'))
        with self.assertRaisesRegex(InvalidProviderResponseError,'OUTSIDE_REPAIR_SCOPE'):
            patch_candidate(candidate,patch(candidate,[change]),obs,request,repair_diagnosis=diag)
        for invalid in (dict(op='request_scope',id='bed',anchor_id='desk',reason_code='I want everything'),
                dict(op='request_scope',id='bed',anchor_id='bed',reason_code='packing_neighbor')):
            with self.assertRaises(InvalidProviderResponseError):
                patch_candidate(candidate,patch(candidate,[invalid,change]),obs,request,repair_diagnosis=diag)
        value=patch(candidate,[change]);value['base_revision']='0'*64
        with self.assertRaisesRegex(InvalidProviderResponseError,'CONSTANT_MISMATCH'):
            patch_candidate(candidate,value,obs,request,repair_diagnosis=diag)

    def test_scope_metadata_only_is_no_change_and_never_replaces_seen_source(self):
        request,obs,candidate,diag=self.scope_case()
        ask=dict(op='request_scope',id='bed',anchor_id='desk',reason_code='packing_neighbor')
        with self.assertRaisesRegex(InvalidProviderResponseError,'SCOPE_REQUIRES_CHANGED_UPDATE'):
            patch_candidate(candidate,patch(candidate,[ask]),obs,request,repair_diagnosis=diag)
        bad=dict(candidate['objects']['bed'],source={'basis':'user'})
        with self.assertRaises(InvalidProviderResponseError):
            patch_candidate(candidate,patch(candidate,[ask,dict(op='update',id='bed',value=bad)]),
                obs,request,repair_diagnosis=diag)

    def test_quality_truncation_stops_once_without_compiler_misclassification(self):
        request,obs,structure,objects,_=photo_case()
        from twinpulse_provider.nebius_pipeline import ChatCompletion
        transport=FixtureTransport([obs.to_dict(),structure,objects,
            ChatCompletion('truncated','fixture','','length',{'completion_tokens':20000})])
        provider=self.provider(transport)
        with self.assertRaises(InvalidProviderResponseError) as caught:
            asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertNotIn('UNMAPPED_COMPILER_ERROR',str(caught.exception))
        self.assertEqual(provider.diagnostic_for(request.request_id)['stage'],'repair')
        self.assertEqual(len(transport.bodies),4)
        self.assertFalse(caught.exception.repairable)

    def test_quality_numeric_progress_then_success_uses_same_budget(self):
        request,obs,structure,objects,candidate=photo_case()
        smaller=dict(candidate['room'],width_m=5)
        middle=patch_candidate(candidate,patch(candidate,[dict(op='room',value=smaller)]),obs,request)
        payload,provenance=compile_scene(middle,obs,request)
        self.assertEqual(review_candidate_quality(middle,payload,provenance,obs,request)['status'],'needs_revision')
        transport=FixtureTransport([obs.to_dict(),structure,objects,
            patch(candidate,[dict(op='room',value=smaller)]),patch(middle,[
                dict(op='update',id='bed',value=dict(objects['bed'],region='rear_left')),
                dict(op='update',id='desk',value=dict(objects['desk'],region='rear_right'))])])
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,store_root=folder)
            result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
            state=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(state['quality_progress']['history'][1]['decision'],'progress')
        self.assertEqual(result.provider_provenance['budget']['repairs'],2)
        self.assertEqual(result.provider_provenance['budget']['stalled_repairs'],0)

    def test_stalled_quality_preserves_latest_valid_candidate_and_original_stop_counters(self):
        request,obs,structure,objects,candidate=photo_case()
        middle=patch_candidate(candidate,patch(candidate,[dict(op='update',id='bed',
            value=dict(objects['bed'],dimensions_m=[1.3,2,.9]))]),obs,request)
        transport=FixtureTransport([obs.to_dict(),structure,objects,
            patch(candidate,[dict(op='update',id='bed',value=middle['objects']['bed'])]),
            patch(middle,[dict(op='update',id='bed',value=dict(objects['bed'],dimensions_m=[1.2,2,.9]))])])
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,store_root=folder)
            result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
            state=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertNotEqual(revision(state['draft']),revision(candidate))
        self.assertEqual(state['draft_refinement']['candidate_revision'],revision(state['draft']))
        self.assertEqual(len(state['patches']),2)
        self.assertEqual(state['budget']['repairs'],2)
        self.assertEqual(state['compiled_plan'],result.plan.to_dict())
        self.assertEqual(state['draft_refinement']['geometry_checks']['candidate_revision'],revision(state['draft']))
        self.assertEqual(state['draft_refinement']['quality_review']['status'],'needs_revision')

    def test_strict_compiler_support_scope_is_host_checked_and_fully_recompiled(self):
        from twinpulse_provider.semantic_scene import compiler_diagnosis
        request=text_request('Estimated room with bed desk and equipment')
        obs=empty_observation()
        structure=dict(summary='Synthetic support conflict',room=dict(width_m=8,length_m=8,height_m=2.6),
            inventory=[dict(id=i,kind=k,evidence_ref='text:0') for i,k in
                [('bed','bed'),('desk','desk'),('device','small_equipment')]])
        objects=dict(bed=dict(bed(),region='rear_left'),desk=dict(desk('middle_right'),dimensions_m=[2,1.4,.74]),
            device=dict(region='rear_left',yaw_deg=0,model_id='common.small_equipment',
                dimensions_m=[1.5,.5,.2],variant='standard',finish='catalog_default',
                placement=dict(relation='surface',parent_id='bed',part='mattress',anchor='centre',elevation_m=None)))
        candidate=checked_batch(objects,scene_draft(checked_structure(structure,request,obs,bound=True)),list(objects))
        try:compile_scene(candidate,obs,request)
        except (ValueError,InvalidProviderResponseError) as error:diag=compiler_diagnosis(error,candidate,request)
        else:self.fail('support fixture must fail')
        _,options=scope_options(candidate,diag)
        self.assertTrue(any(r['id']=='desk' and r['anchor_id']=='device' for r in options),(diag,options))
        operations=[dict(op='request_scope',id='desk',anchor_id='device',reason_code='support_alternative'),
            dict(op='update',id='desk',value=dict(objects['desk'],dimensions_m=[2.1,1.4,.74])),
            dict(op='update',id='device',value=dict(objects['device'],placement=dict(
                relation='surface',parent_id='desk',part='top',anchor='centre',elevation_m=None)))]
        transport=FixtureTransport([structure,objects,patch(candidate,operations)])
        provider=self.provider(transport)
        # This existing scope-repair case intentionally exercises the strict
        # compiler contract. Ordinary progressive generation now retains this
        # native prop as draft-only pending (covered by ProgressiveTwinTests).
        # No valid plan/check result is injected: every phase still runs.
        from unittest.mock import patch as strict_mode
        def strict_compile(*args,**kwargs):
            kwargs['progressive']=False
            return compile_scene(*args,**kwargs)
        with strict_mode('twinpulse_provider.budgeted_pipeline.compile_scene',side_effect=strict_compile):
            result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        evidence=result.provider_provenance['patches'][0]['scope_decision']
        self.assertEqual(evidence['accepted'][0]['id'],'desk')
        self.assertTrue(result.provider_provenance['checks_complete'])
        self.assertEqual(result.provider_provenance['budget']['repairs'],1)
        self.assertEqual(len(transport.bodies),3)

    def test_public_scope_diagnostics_are_typed_and_do_not_leak_prose(self):
        from twinpulse_app.product_workflow_service import _public_generation_diagnostics
        public=_public_generation_diagnostics(dict(repair_decision=dict(decision='progress',repair_kind='quality'),
            scope_decision=dict(schema_version='geometry-scope-1.0',physical_authority=True,
                secret='private',accepted=[dict(id='desk',anchor_id='device',reason_code='support_alternative',
                    evidence='private'),dict(id='secret:unsafe',anchor_id='device',reason_code='support_alternative'),
                    dict(id='arbitrary',anchor_id='device',reason_code='free-text-reason')])))
        self.assertEqual(public['repair_decision']['repair_kind'],'quality')
        self.assertEqual(public['scope_decision']['accepted'],[
            dict(id='desk',anchor_id='device',reason_code='support_alternative')])
        self.assertFalse(public['scope_decision']['physical_authority'])
        self.assertNotIn('private',json.dumps(public))

    def test_quality_continuation_keeps_seen_history_budget_and_original_checkpoint(self):
        from twinpulse_provider.nebius_pipeline import ChatCompletion
        from twinpulse_provider.generation_policy import GenerationPolicy
        from twinpulse_app.generation_scope import OrdinaryInferenceScope
        from twinpulse_provider.generation_store import input_digest
        from twinpulse_core import canonical_sha256
        request,obs,structure,objects,candidate=photo_case()
        with TemporaryDirectory() as folder:
            root=Path(folder)
            provider=self.provider(FixtureTransport([obs.to_dict(),structure,objects,
                ChatCompletion('length',fixtures.PLANNER_MODEL,'','length',{})]),store_root=root/'store')
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
            key=provider.diagnostic_for(request.request_id)['checkpoint_id']
            parent=provider.store.read('checkpoint',key)
            scope=OrdinaryInferenceScope('ordinary-generation:offline-quality-continuation',input_digest(request),
                'b'*64,GenerationPolicy().sha256,root/'fixture-ledger.json',{
                    fixtures.PLANNER_MODEL:dict(input_per_million=1,output_per_million=1,
                        context_tokens=40000,source='fixture-not-live')},'1',12,
                approved_checkpoint_sha256=canonical_sha256(parent))
            continued=replace(request,request_id='quality-resumed',inference_scope=scope,continuation_checkpoint=key)
            next_transport=FixtureTransport([patch(candidate,[
                dict(op='update',id='bed',value=dict(objects['bed'],region='rear_left')),
                dict(op='update',id='desk',value=dict(objects['desk'],region='rear_right'))])])
            next_provider=self.provider(next_transport,store_root=root/'store',route_sha256='b'*64)
            result=asyncio.run(GenerationService(next_provider,config(timeout_s=300),plan_version='2.2').generate(continued))
            state=next_provider.store.read('checkpoint',next_provider.diagnostic_for(continued.request_id)['checkpoint_id'])
            self.assertEqual(provider.store.read('checkpoint',key),parent)
        self.assertEqual(len(next_transport.bodies),1)
        self.assertEqual(result.provider_provenance['budget']['repairs'],2)
        self.assertEqual(result.provider_provenance['budget']['cumulative_requests'],5)
        self.assertEqual(state['quality_progress']['history'][1]['decision'],'repeated_candidate')
        self.assertEqual(state['quality_progress']['history'][-1]['decision'],'progress')

    def test_scope_duplicate_or_dimension_change_cannot_evade_validation(self):
        request,obs,candidate,diag=self.scope_case()
        ask=dict(op='request_scope',id='bed',anchor_id='desk',reason_code='packing_neighbor')
        with self.assertRaisesRegex(InvalidProviderResponseError,'SCOPE_REQUEST_REJECTED'):
            patch_candidate(candidate,patch(candidate,[ask,ask,dict(op='update',id='bed',
                value=dict(candidate['objects']['bed'],region='middle_right'))]),obs,request,repair_diagnosis=diag)
        measured=replace(request,prompt='A 6x6m room with bed and desk')
        changed=patch_candidate(candidate,patch(candidate,[dict(op='room',
            value=dict(candidate['room'],width_m=5))]),obs,measured,repair_diagnosis=diag)
        with self.assertRaisesRegex(ValueError,'USER_DIMENSIONS_CHANGED'):compile_scene(changed,obs,measured)

    def test_quality_patch_geometry_regression_is_not_published_as_a_photo_fix(self):
        from twinpulse_provider.nebius_pipeline import ChatCompletion
        request,obs,structure,objects,candidate=photo_case()
        invalid=dict(objects['bed'],dimensions_m=[1.4,2,3])
        transport=FixtureTransport([obs.to_dict(),structure,objects,
            patch(candidate,[dict(op='update',id='bed',value=invalid)]),
            ChatCompletion('length','fixture','','length',{})])
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,store_root=folder)
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
            state=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(state['patches'][0]['validation'],'failed')
        self.assertEqual(state['budget']['repairs'],2)
        self.assertIsNone(state['compiled_plan'])
        self.assertEqual(len(transport.bodies),5)
        self.assertEqual(state['state'],'DRAFT_INCOMPLETE')
        self.assertEqual(revision(state['draft']),revision(candidate))
