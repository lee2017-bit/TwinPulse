# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit zero-network render/critic fixtures; never photo fidelity evidence."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
from io import BytesIO
from tempfile import TemporaryDirectory
import unittest

import test_budgeted_generation as fixtures
import test_scope_quality_loop as quality_fixtures
from twinpulse_provider import GenerationService, ProviderConfigurationError
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy, ExecutionBudget, GenerationBudgetError
from twinpulse_provider.render_review import schema, checked, binding, RENDER_REVIEW_REVISION
from twinpulse_provider.semantic_scene import compile_scene, revision
from twinpulse_provider.scene_contract import SceneContractError
from twinpulse_provider.nebius_pipeline import ChatCompletion
from twinpulse_app.product_workflow_service import _public_generation_diagnostics


class ApprovedFixtureScope:
    approved_render_review=True
    approval_id='fixture-not-live'
    cache_identity='fixture-render'
    def bind(self,*args):return None


class CaptureFixture:
    def __init__(self):self.captures=[];self.stale=False
    def preflight(self):pass
    def assert_current(self,metadata):
        if self.stale:raise ProviderConfigurationError('RENDER_REVIEW_SUPERSEDED')
    async def capture(self,plan,candidate_revision,token,timeout_s):
        from PIL import Image
        stream=BytesIO();Image.new('RGB',(64,64),'white').save(stream,format='JPEG')
        jpeg=stream.getvalue()
        from twinpulse_core import canonical_sha256
        result=dict(jpeg=jpeg,metadata=dict(sha256=hashlib.sha256(jpeg).hexdigest(),
            plan_sha256=canonical_sha256(plan),candidate_revision=candidate_revision,
            applied_revision=canonical_sha256(plan),scene_revision=canonical_sha256(plan),
            engine_session_id='fixture-engine',stage_epoch='fixture-epoch',frame_id=len(self.captures)+1,
            command_id='fixture-command-'+str(len(self.captures))))
        self.captures.append(deepcopy(result));return result


def review_response(body, *, contradiction=False, uncertain=False):
    props=body['response_format']['json_schema']['schema']['properties']
    constant=lambda field:props[field].get('const',(props[field].get('enum') or [None])[0])
    return dict(review_version=constant('review_version'),frame_key=constant('frame_key'),
        objects={identity:{aspect:dict(status=('contradiction' if contradiction and identity=='bed' and aspect=='layout'
            else 'uncertain' if uncertain else 'consistent'),confidence=.9,reason='Explicit fixture, not a visual judgement.')
            for aspect in ('layout','support','appearance')} for identity in props['objects']['properties']})


class DynamicFixtureTransport(fixtures.FixtureTransport):
    async def complete(self,body,token,config):
        if self.responses and callable(self.responses[0]):
            self.responses[0]=self.responses[0](body)
        return await super().complete(body,token,config)


class TextRenderContractTests(unittest.TestCase):
    def test_only_exact_flash_critic_disables_hidden_reasoning_without_dropping_checks(self):
        from twinpulse_provider.render_review import body, ASPECTS
        request, port, obs, _, _, draft = case()
        plan, _ = compile_scene(draft, obs, request)
        capture = asyncio.run(port.capture(plan, revision(draft), None, 300));capture['plan'] = plan
        flash = body(request, draft, obs, capture, model='deepseek-ai/DeepSeek-V4.1-Flash', cap=40000)
        self.assertEqual(flash['reasoning_effort'], 'none')
        self.assertEqual(flash['max_tokens'], 40000)
        objects = flash['response_format']['json_schema']['schema']['properties']['objects']
        self.assertEqual(set(objects['required']), set(draft['objects']))
        self.assertTrue(all(set(row['required']) == set(ASPECTS) for row in objects['properties'].values()))
        for model in ('fixture', 'deepseek-ai/DeepSeek-V4.1-Flash-other', 'nvidia/nemotron-3-super-120b-a12b'):
            other = body(request, draft, obs, capture, model=model, cap=40000)
            self.assertNotIn('reasoning_effort', other)
            self.assertEqual(other['response_format'], flash['response_format'])

    def test_compact_review_keeps_semantic_inventory_without_duplicate_recipe_trees(self):
        from twinpulse_provider.render_review import review_candidate,repair_geometry_context
        request,port,obs,structure,objects,draft=case()
        draft['model_recipes']={'large_definition':{'parts':['not needed twice']*100}}
        compact=review_candidate(draft)
        self.assertEqual(compact['inventory'],draft['inventory']);self.assertEqual(compact['objects'],draft['objects'])
        self.assertNotIn('model_recipes',compact)
        draft.pop('model_recipes');plan,_=compile_scene(draft,obs,request)
        target=plan['calls'][-1]['arguments']['id']
        context=repair_geometry_context(plan,[target])
        self.assertEqual([r['arguments']['id'] for r in context['target_calls']],[target])
        self.assertEqual(context['plan_sha256'],__import__('twinpulse_core').canonical_sha256(plan))
        self.assertIn('Only schema repair_scope',context['permission'])

    def test_text_reference_sends_one_bound_render_not_a_fabricated_source_photo(self):
        from twinpulse_provider.render_review import body
        request,port,obs,structure,objects,draft=case()
        request=replace(request,images=(),prompt='Two unequal shelves with no side walls')
        plan,_=compile_scene(draft,obs,request)
        capture=asyncio.run(port.capture(plan,revision(draft),None,300));capture['plan']=plan
        wire=body(request,draft,obs,capture,model=fixtures.OBSERVER_MODEL,cap=40000)
        self.assertEqual(sum(v.get('type')=='image_url' for v in wire['messages'][1]['content']),1)
        self.assertIn('explicit user request',wire['messages'][0]['content'])
        result=review_response(wire);target=next(iter(result['objects']))
        result['objects'][target]['appearance'].update(status='contradiction',confidence=.95)
        diagnosis=checked(result,draft,plan,capture,dict(issues=[],comparison_source='user_request_and_current_render'))
        self.assertEqual(diagnosis['issues'][0]['expected']['source'],'user_request_and_current_render')


def case():
    request,observation,structure,objects,candidate=quality_fixtures.photo_case()
    value=observation.to_dict();value['relations']=[]
    # Current raw observer wire; original fixture facts and IDs are unchanged.
    value['schema_version']='1.5'
    from twinpulse_provider.observation_alignment import unknown_alignment
    for row in value['entities']:
        row['instance_count']=1
        row['footprint_alignment']=unknown_alignment()
    from twinpulse_provider.nebius_pipeline import ObservationArtifact
    observation=ObservationArtifact.from_mapping(value)
    port=CaptureFixture()
    request=replace(request,inference_scope=ApprovedFixtureScope(),render_review_port=port)
    return request,port,observation,structure,objects,candidate


def provider(transport,**kwargs):
    return BudgetedPipeline(transport,policy=replace(GenerationPolicy(),external_final_review=True),
        observer_model_id=fixtures.OBSERVER_MODEL,planner_model_id=fixtures.PLANNER_MODEL,
        site_plan_version='2.2',stage_output_token_caps={'observer':4000,'planner':20000},**kwargs)


def pending_case():
    from twinpulse_provider.nebius_pipeline import ObservationArtifact
    from twinpulse_provider.semantic_scene import checked_structure,scene_draft,checked_batch
    request,port,observation,structure,objects,_=case()
    raw=observation.to_dict()
    raw['entities'].append(dict(id='seen_cover',kind='static_obstacle',description='Synthetic oversized supported cover',
        confidence=.9,role='object',category='surface_covering',region='unknown',spatial_confidence=.9,instance_count=1,
        footprint_alignment=__import__('twinpulse_provider.observation_alignment',fromlist=['unknown_alignment']).unknown_alignment()))
    observation=ObservationArtifact.from_mapping(raw)
    structure['inventory'].append(dict(id='cover',kind='surface_covering',evidence_ref='seen:seen_cover'))
    objects['cover']=dict(region='rear_right',yaw_deg=0,model_id='common.surface_covering',
        dimensions_m=[2.5,2.5,.03],variant='standard',finish='catalog_default',
        placement=dict(relation='surface',parent_id='bed',part='mattress',anchor='centre',elevation_m=None))
    candidate=checked_batch(objects,scene_draft(checked_structure(structure,request,observation,bound=True)),list(objects))
    return request,port,observation,structure,objects,candidate


class RenderReviewTests(unittest.TestCase):
    def test_public_retention_recheck_is_typed_not_raw_search_or_quality_authority(self):
        for passed in (True,False):
            raw=dict(validation='passed' if passed else 'failed',gate='exact_plan_and_support_witness',
                same_plan=True,same_witness=passed,physical_authority=False,
                fresh_search_statistics=[{'untrusted':'not public'}],retained_witness_sha256='a'*64)
            public=_public_generation_diagnostics({'retention_revalidation':raw})['retention_revalidation']
            self.assertEqual(set(public),{'validation','gate','same_plan','same_witness','physical_authority'})
            self.assertEqual(public['validation'],raw['validation']);self.assertNotIn('photo_quality',public)
            for field,value in (('same_witness',1),('physical_authority',True),('gate','other'),
                                ('validation','failed' if passed else 'passed')):
                with self.subTest(passed=passed,field=field):
                    invalid={**raw,field:value}
                    self.assertNotIn('retention_revalidation',_public_generation_diagnostics(
                        {'retention_revalidation':invalid}))

    def test_subset_revalidation_evidence_records_pass_and_failed_gate(self):
        from contextlib import nullcontext
        from unittest.mock import patch
        for changed in (False,True):
            request,port,observation,structure,objects,candidate=pending_case()
            operation=quality_fixtures.patch(candidate,[dict(op='update',id='bed',
                value=dict(objects['bed'],region='front_right'))])
            transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,
                lambda b:review_response(b,contradiction=True),operation,review_response])
            recorded=[]
            transport.record_validation=lambda name,identity,record:recorded.append((name,deepcopy(record)))
            pipeline=provider(transport);pipeline.policy=replace(pipeline.policy,max_repairs=1)
            guard=(patch('twinpulse_provider.partial_refinement.same_support_witness',return_value=False)
                if changed else nullcontext())
            with self.subTest(changed=changed),guard:
                invocation=GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request)
                if changed:
                    with self.assertRaisesRegex(GenerationBudgetError,'QUALITY_REPAIR_LIMIT_REACHED'):
                        asyncio.run(invocation)
                else:asyncio.run(invocation)
                result=next(record for name,record in recorded if name=='support_subset_revalidation')
                self.assertEqual(result['validation'],'failed' if changed else 'passed')
                self.assertTrue(result['same_plan']);self.assertEqual(result['same_witness'],not changed)
                self.assertEqual(result['original_failure'],'QUALITY_REPAIR_LIMIT_REACHED')
                self.assertIn('fresh_search_statistics',result);self.assertIn('retained_search_statistics',result)
                self.assertFalse(result['physical_authority'])
                self.assertEqual(pipeline._budget.repairs,1);self.assertEqual(len(transport.bodies),6)
                if changed:self.assertNotIn('draft_refinement',pipeline.diagnostic_for(request.request_id))

    def test_nested_pending_gets_current_review_and_strict_subset_without_flattening(self):
        from twinpulse_provider.nebius_pipeline import ObservationArtifact
        from twinpulse_provider.semantic_scene import checked_structure,scene_draft,checked_batch
        request,port,observation,structure,objects,_=pending_case()
        raw=observation.to_dict();raw['entities'].append(dict(id='seen_nested',kind='static_obstacle',
            description='Explicit synthetic supported prop',confidence=.9,role='object',
            category='tabletop_item',region='unknown',spatial_confidence=.9,instance_count=1,
            footprint_alignment=__import__('twinpulse_provider.observation_alignment',fromlist=['unknown_alignment']).unknown_alignment()))
        observation=ObservationArtifact.from_mapping(raw)
        structure['inventory'].append(dict(id='nested',kind='tabletop_item',evidence_ref='seen:seen_nested'))
        objects['nested']=dict(region='rear_right',yaw_deg=0,model_id='common.tabletop_item',
            dimensions_m=[.1,.1,.1],variant='standard',finish='catalog_default',
            placement=dict(relation='surface',parent_id='cover',part='top',anchor='centre',elevation_m=None))
        candidate=checked_batch(objects,scene_draft(checked_structure(structure,request,observation,bound=True)),list(objects))
        operation=quality_fixtures.patch(candidate,[dict(op='update',id='bed',
            value=dict(objects['bed'],dimensions_m=[1.3,2.,.9]))])
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,review_response,operation,review_response])
        pipeline=provider(transport);pipeline.policy=replace(pipeline.policy,max_repairs=1)
        result=asyncio.run(GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
        provenance=result.provider_provenance;witness=provenance['progressive_twin']
        self.assertEqual(witness['schema_version'],'progressive-twin-1.2')
        self.assertEqual({r['id'] for r in witness['unresolved']},{'cover','nested'})
        nested=next(r for r in witness['unresolved'] if r['id']=='nested')
        self.assertEqual(nested['parent_id'],'cover');self.assertEqual(nested['materialized_anchor_id'],'bed')
        self.assertEqual(provenance['draft_refinement']['schema_version'],'draft-refinement-1.1')
        self.assertEqual(provenance['draft_refinement']['stop_reason'],'QUALITY_REPAIR_LIMIT_REACHED')
        self.assertEqual(provenance['quality_review']['render_comparison'],'reviewed')
        self.assertEqual(len(provenance['render_history']),2)
        self.assertTrue(all(r['target_ids']==['bed'] for r in provenance['quality_review']['issues']))
        self.assertEqual(len(transport.bodies),6)

    def test_pending_support_gets_current_visual_review_before_any_repair(self):
        request,port,observation,structure,objects,candidate=pending_case()
        operation=quality_fixtures.patch(candidate,[dict(op='update',id='bed',
            value=dict(objects['bed'],region='front_right'))])
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,
            lambda b:review_response(b,contradiction=True),operation,review_response])
        pipeline=provider(transport)
        pipeline.policy=replace(pipeline.policy,max_repairs=1)
        result=asyncio.run(GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
        provenance=result.provider_provenance
        self.assertEqual([r['role'] for r in provenance['budget']['attempts']],
            ['initial']*3+['final_review','repair','final_review'])
        self.assertEqual(provenance['budget']['repairs'],1)
        self.assertEqual(provenance['quality_review']['render_comparison'],'reviewed')
        self.assertEqual(provenance['quality_review']['relative_layout']['status'],'consistent_materialized_anchors')
        self.assertEqual(provenance['quality_review']['relative_layout']['deferred_object_ids'],['cover'])
        self.assertEqual(provenance['draft_refinement']['stop_reason'],'QUALITY_REPAIR_LIMIT_REACHED')
        self.assertEqual(provenance['draft_refinement']['schema_version'],'draft-refinement-1.1')
        self.assertIn('PHOTO_PENDING_SUPPORT_NEEDS_REVISION',{r['code'] for r in provenance['quality_review']['issues']})
        self.assertNotIn('cover',{r.arguments['id'] for r in result.plan.calls})
        self.assertEqual(len(provenance['progressive_twin']['inventory']),3)
        self.assertEqual(len(port.captures),2)

    def test_invalid_complete_repair_stall_preserves_current_review_and_original_pending(self):
        request,port,observation,structure,objects,candidate=pending_case()
        nochange=quality_fixtures.patch(candidate,[])
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,
            lambda b:review_response(b,contradiction=True),nochange,nochange])
        pipeline=provider(transport)
        result=asyncio.run(GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
        provenance=result.provider_provenance
        self.assertEqual(provenance['draft_refinement']['stop_reason'],'REPAIR_STALLED')
        self.assertEqual(provenance['quality_review']['render_comparison'],'reviewed')
        self.assertEqual(provenance['quality_review']['relative_layout']['status'],'needs_revision')
        self.assertEqual(provenance['quality_review']['progressive_sha256'],provenance['progressive_twin']['sha256'])
        self.assertEqual(provenance['progressive_twin']['unresolved'][0]['id'],'cover')
        self.assertIn('RENDER_LAYOUT_MISMATCH',{r['code'] for r in provenance['quality_review']['issues']})
        self.assertEqual(len(transport.bodies),6)
        self.assertEqual(len(port.captures),1)

    def test_visual_layout_scope_uses_only_bound_observation_pairs(self):
        from twinpulse_provider.render_review import body
        from twinpulse_provider.semantic_scene import review_candidate_quality
        request,observation,structure,objects,candidate=quality_fixtures.photo_case()
        port=CaptureFixture();plan,provenance=compile_scene(candidate,observation,request)
        capture=asyncio.run(port.capture(plan,revision(candidate),None,1));capture['plan']=plan
        quality=review_candidate_quality(candidate,plan,provenance,observation,request)
        wire=body(request,candidate,observation,capture,model=fixtures.OBSERVER_MODEL,cap=4000)
        result=checked(review_response(wire,contradiction=True),candidate,plan,capture,quality)
        problem=next(r for r in result['issues'] if r['code']=='RENDER_LAYOUT_MISMATCH')
        self.assertEqual(problem['related_ids'],['desk'])
        self.assertEqual(result['relative_layout']['status'],'needs_revision')
        self.assertFalse(result['relative_layout']['physical_authority'])
        self.assertEqual(result['relative_layout']['sensor_alignment'],'not_run')

    def test_engine_change_during_invalid_repairs_cannot_save_reviewed_subset_as_current(self):
        request,port,observation,structure,objects,candidate=pending_case()
        nochange=quality_fixtures.patch(candidate,[])
        def stale_repair(body):port.stale=True;return nochange
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,
            lambda b:review_response(b,contradiction=True),nochange,stale_repair])
        pipeline=provider(transport)
        with self.assertRaisesRegex(ProviderConfigurationError,'SUPERSEDED'):
            asyncio.run(GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertNotIn('draft_refinement',pipeline.diagnostic_for(request.request_id))
        self.assertEqual(len(transport.bodies),6)

    def test_consistent_critic_cannot_erase_deterministic_photo_conflict(self):
        request,port,observation,structure,objects,candidate=case()
        payload,_=compile_scene(candidate,observation,request)
        capture=asyncio.run(port.capture(payload,revision(candidate),None,1));capture['plan']=payload
        from twinpulse_provider.render_review import body
        review_body=body(request,candidate,observation,capture,model=fixtures.OBSERVER_MODEL,cap=4000)
        conflict=dict(code='PHOTO_OBSERVED_REGION_CONTRADICTION',target_ids=['bed'],related_ids=[])
        result=checked(review_response(review_body),candidate,payload,capture,dict(status='needs_revision',issues=[conflict]))
        self.assertEqual(result['status'],'needs_revision');self.assertIn(conflict,result['issues'])

    def test_current_render_failure_patch_compile_recapture_same_budget(self):
        request,port,observation,structure,objects,candidate=case()
        patch=quality_fixtures.patch(candidate,[dict(op='update',id='bed',value=dict(objects['bed'],region='front_right'))])
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,
            lambda b:review_response(b,contradiction=True),patch,review_response])
        with TemporaryDirectory() as root:
            pipeline=provider(transport,store_root=root)
            result=asyncio.run(GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
            diag=pipeline.diagnostic_for(request.request_id)
            saved=pipeline.store.read('checkpoint',diag['checkpoint_id'])
            self.assertEqual(diag['budget']['requests'],6);self.assertEqual(diag['budget']['repairs'],1)
            self.assertEqual([r['role'] for r in diag['budget']['attempts']],['initial']*3+['final_review','repair','final_review'])
            self.assertEqual(len(port.captures),2)
            self.assertNotEqual(port.captures[0]['metadata']['candidate_revision'],port.captures[1]['metadata']['candidate_revision'])
            self.assertEqual(saved['render_history'][-1]['status'],'consistent')
            self.assertEqual(saved['stage_acceptance']['SIM_Run_Stop'],'not_run')
            self.assertEqual(saved['stage_acceptance']['Isaac_Build'],'preview_passed')
            self.assertEqual(saved['Build'],'PREVIEW_ONLY')
            self.assertEqual(saved['render_capture'],saved['render_history'][-1]['capture'])
            self.assertEqual(result.provider_provenance['quality_review']['candidate_revision'],revision(saved['draft']))
            evidence=pipeline.store.read('render',saved['render_history'][-1]['frame_key'])
            self.assertIn('jpeg_base64',evidence)
            self.assertNotIn('data:image',__import__('json').dumps(transport.bodies[4]))
            critic=transport.bodies[3]
            self.assertEqual(critic['model'],fixtures.OBSERVER_MODEL)
            self.assertEqual(critic['max_tokens'],4000)
            self.assertEqual(sum(x.get('type')=='image_url' for x in critic['messages'][-1]['content']),2)

    def test_uncertain_does_not_force_repair_or_claim_metric_pass(self):
        request,port,observation,structure,objects,candidate=case()
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,lambda b:review_response(b,uncertain=True)])
        pipeline=provider(transport)
        result=asyncio.run(GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(result.provider_provenance['quality_review']['status'],'uncertain')
        self.assertEqual(result.provider_provenance['quality_review']['metric_scale'],'estimated_not_measured')
        self.assertEqual(pipeline._budget.repairs,0)

    def test_stale_engine_after_critic_never_publishes_or_repairs(self):
        request,port,observation,structure,objects,candidate=case()
        def stale(body):port.stale=True;return review_response(body)
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,stale])
        with self.assertRaisesRegex(ProviderConfigurationError,'SUPERSEDED'):
            asyncio.run(GenerationService(provider(transport),fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(len(transport.bodies),4)

    def test_missing_ids_or_wrong_frame_rejected_without_automatic_critic_retry(self):
        for mutation in ('frame','missing','extra'):
            request,port,observation,structure,objects,candidate=case()
            def invalid(body):
                value=review_response(body)
                if mutation=='frame':value['frame_key']='0'*64
                elif mutation=='missing':value['objects'].pop('bed')
                else:value['objects']['unknown']=value['objects']['bed']
                return value
            transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,invalid])
            with self.assertRaises(SceneContractError):
                asyncio.run(GenerationService(provider(transport),fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
            self.assertEqual(len(transport.bodies),4)

    def test_render_length_stops_immediately(self):
        request,port,observation,structure,objects,candidate=case()
        transport=DynamicFixtureTransport([observation.to_dict(),structure,objects,
            ChatCompletion('length',fixtures.OBSERVER_MODEL,'{}','length',{})])
        pipeline=provider(transport)
        with self.assertRaisesRegex(fixtures.InvalidProviderResponseError,'truncated'):
            asyncio.run(GenerationService(pipeline,fixtures.config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(pipeline._budget.terminal,'PROVIDER_OUTPUT_TRUNCATED')
        self.assertEqual(pipeline._budget.repairs,0)

    def test_selected_review_text_only_needs_no_engine_or_photo(self):
        transport=DynamicFixtureTransport([fixtures.wire_structure(),{'bed':fixtures.bed()}])
        result=asyncio.run(GenerationService(provider(transport),fixtures.config(timeout_s=300),plan_version='2.2').generate(fixtures.text_request()))
        self.assertEqual(result.provider_provenance['quality_review']['status'],'not_applicable')
        self.assertEqual(len(transport.bodies),2)

    def test_two_reviews_share_time_reserve_and_next_repair_requires_review_slot(self):
        clock=fixtures.Clock();budget=ExecutionBudget(replace(GenerationPolicy(),external_final_review=True),clock=clock)
        identity=budget.reserve({'model':'fixture','max_tokens':1},role='final_review')
        clock.now=60;budget.settle(identity,status='received')
        with self.assertRaisesRegex(GenerationBudgetError,'NEEDS_TIME_BUDGET'):budget.timeout_for('final_review')
        budget=ExecutionBudget(replace(GenerationPolicy(),external_final_review=True,max_requests=5,max_repairs=1))
        budget.carried_requests=4
        with self.assertRaisesRegex(GenerationBudgetError,'NEEDS_REQUEST_BUDGET'):
            budget.reserve({'model':'fixture','max_tokens':1},role='repair')

    def test_render_hash_tampering_rejected(self):
        request,port,observation,structure,objects,candidate=case()
        plan,_=compile_scene(candidate,observation,request)
        capture=asyncio.run(port.capture(plan,revision(candidate),None,1))
        capture['jpeg']+=b'changed'
        with self.assertRaisesRegex(ProviderConfigurationError,'IDENTITY_INVALID'):binding(candidate,plan,capture)

    def test_public_dto_keeps_only_typed_review_not_critic_prose_or_image(self):
        result=_public_generation_diagnostics(dict(stage_acceptance={'photo_quality':'consistent','Isaac_Build':'preview_passed'},
            quality_review=dict(schema_version=RENDER_REVIEW_REVISION,status='consistent',render_comparison='reviewed',
                frame_key='a'*64,issues=[],assessments={'secret':'untrusted prose'},jpeg_base64='not-public')))
        self.assertEqual(result['quality_review']['frame_key'],'a'*64)
        self.assertNotIn('assessments',result['quality_review'])
        self.assertNotIn('jpeg_base64',result['quality_review'])
