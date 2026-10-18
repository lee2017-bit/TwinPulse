# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Preview contracts and retained work; explicit fixtures, no paid endpoint."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import test_budgeted_generation as f
from test_inventory_work import many_objects
from test_observation_instances import grouped
from twinpulse_core import canonical_sha256, execute_site_tool_plan, SiteToolPlan
from twinpulse_provider import GenerationService, ImageInput, InvalidProviderResponseError
from twinpulse_provider.nebius_pipeline import ObservationArtifact, ChatCompletion
from twinpulse_provider.observation_instances import expand_observation_instances
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.generation_preview import compile_generation_preview, parameter_order, checked_room_seed, compile_room_seed
from twinpulse_provider.semantic_scene import checked_structure, checked_batch, scene_draft, compile_scene


class PreviewPort:
    supports_incremental_preview=True
    def __init__(self):
        self.engine_identity=None;self.plans=[];self.broker=Mock()
        self.broker.has_pending_operations.return_value=False
    def preflight(self):self.engine_identity=('fixture','fixture')
    async def capture(self,plan,candidate_revision,token,timeout_s):
        self.plans.append(deepcopy(plan))
        scene=execute_site_tool_plan(SiteToolPlan.from_dict(plan),source='photo',source_ref='a'*64).scene
        self.last=dict(candidate_revision=candidate_revision,scene_revision=scene.revision,
            plan_sha256=canonical_sha256(plan),preview_only=True,physical_authority=False)
        return dict(metadata=deepcopy(self.last),jpeg=b'explicit-fixture-not-Isaac')
    def assert_current(self,metadata):assert metadata==self.last


class GenerationPreviewTests(unittest.TestCase):
    def test_invalid_parent_defers_only_its_dependency_closure(self):
        request=f.text_request('Create a bed, storage and a bag in an estimated room')
        inventory=f.structure()['inventory']+[dict(id=i,kind=k,source=dict(
            basis='user',observation_ids=[],user_quote=quote)) for i,k,quote in
            [('cabinet','storage','storage'),('bag','bag','a bag')]]
        draft=scene_draft(checked_structure({**f.structure(),'inventory':inventory},request,f.empty_observation()))
        cabinet=dict(f.bed(),model_id='common.storage',dimensions_m=[.8,.2,.6],variant='open')
        bag=dict(f.bed(),model_id='common.bag',dimensions_m=[.1,.1,.1],variant='standard',finish='catalog_default',
            placement=dict(relation='surface',parent_id='cabinet',part='body',anchor='centre',elevation_m=None))
        draft=checked_batch(dict(bed=f.bed(),cabinet=cabinet,bag=bag),draft,['bed','cabinet','bag'])
        original=deepcopy(draft)
        plan,_,progress=compile_generation_preview(draft,f.empty_observation(),request)
        self.assertEqual(draft,original)
        self.assertEqual(progress['rendered_count'],1);self.assertEqual(progress['pending_count'],2)
        pending={row['id']:row for row in progress['pending_objects']}
        self.assertEqual(pending['bag']['blocked_by'],['cabinet'])
        self.assertEqual(pending['bag']['reason_code'],'PARENT_VALIDATION_PENDING')
        self.assertIn('bed',{row['arguments']['id'] for row in plan['calls']})
        with self.assertRaises(ValueError):compile_scene(draft,f.empty_observation(),request)

    def test_room_seed_is_checked_without_inventing_inventory_completion(self):
        request=f.text_request('Create a bed in a 5 by 6 metre room')
        seed=dict(summary='Estimated room shell',room=dict(width_m=5,length_m=6,height_m=2.6))
        plan,progress=compile_room_seed(seed,f.empty_observation(),request)
        self.assertEqual(len(plan['calls']),4);self.assertEqual(progress['rendered_count'],0)
        self.assertFalse(progress['physical_authority'])
        with self.assertRaises(InvalidProviderResponseError):
            checked_room_seed({**seed,'room':{**seed['room'],'width_m':7}},f.empty_observation(),request)

    def test_major_objects_scheduled_without_changing_inventory(self):
        draft=f.draft();minor=dict(id='trinket',kind='unknown',source=dict(basis='inferred',observation_ids=[],user_quote=None))
        draft['inventory'].insert(0,minor);original=deepcopy(draft['inventory'])
        self.assertEqual(parameter_order(draft,f.empty_observation()),['bed','trinket'])
        self.assertEqual(draft['inventory'],original)

    def provider(self,transport,folder,policy=None):
        return f.BudgetedPipeline(transport,policy=policy or replace(GenerationPolicy(),external_final_review=False),
            store_root=folder,observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,
            site_plan_version='2.2',planner_template_no_thinking=True)

    def test_explicit_resume_rebuilds_checked_best_without_renewing_exhausted_repairs(self):
        from pathlib import Path
        from test_geometry_repair_loop import fixture
        from twinpulse_provider.generation_policy import GenerationBudgetError
        from twinpulse_provider.generation_store import input_digest
        from twinpulse_app.generation_scope import OrdinaryInferenceScope
        shape,parameters,_=fixture()
        policy=replace(GenerationPolicy(),external_final_review=False,max_repairs=1)
        with TemporaryDirectory() as folder:
            root=Path(folder); request=f.text_request(identity='legacy-preview-parent')
            parent_provider=self.provider(f.FixtureTransport([shape,parameters,
                ChatCompletion('length',f.PLANNER_MODEL,'','length',{})]),root/'store',policy)
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(parent_provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            parent_key=parent_provider.diagnostic_for(request.request_id)['checkpoint_id']
            original=parent_provider.store.read('checkpoint',parent_key)
            parent=deepcopy(original);parent['best_preview_snapshot']=None
            legacy_key=canonical_sha256({'legacy_preview_missing':parent_key})
            parent_provider.store.save('checkpoint',legacy_key,parent)
            scope=OrdinaryInferenceScope('ordinary-generation:legacy-preview-resume',input_digest(request),
                'b'*64,policy.sha256,root/'scope.json',{},'1',12,
                approved_checkpoint_sha256=canonical_sha256(parent))
            transport=f.FixtureTransport([]);port=PreviewPort()
            provider=self.provider(transport,root/'store',policy)
            provider.route_sha256='b'*64
            continued=replace(request,request_id='legacy-preview-resumed',inference_scope=scope,
                continuation_checkpoint=legacy_key,render_review_port=port)
            local_activities=[]
            def observed_compile(*args,**kwargs):
                local_activities.append(deepcopy(provider.diagnostic_for(continued.request_id).get('generation_activity')))
                return compile_scene(*args,**kwargs)
            with patch('twinpulse_provider.budgeted_pipeline.compile_scene',side_effect=observed_compile),self.assertRaises(GenerationBudgetError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(continued))
            self.assertEqual(local_activities[0],dict(schema_version='generation-activity-1.0',
                stage='resume_revalidation',phase='validating'))
            diagnostic=provider.diagnostic_for(continued.request_id)
            saved=provider.store.read('checkpoint',diagnostic['checkpoint_id'])
            self.assertEqual(transport.bodies,[])
            self.assertTrue(port.plans)
            self.assertEqual(saved['budget']['requests'],0)
            self.assertEqual(saved['budget']['repairs'],1)
            self.assertEqual(saved['budget']['cumulative_requests'],parent['budget']['cumulative_requests'])
            exact=saved['best_preview_snapshot']
            self.assertIsNotNone(exact,{'revalidation':saved.get('best_local_revalidation'),
                'progress':saved.get('generation_preview'),'decision':saved.get('working_branch')})
            self.assertEqual(exact['capture_metadata']['candidate_revision'],saved['generation_preview']['candidate_revision'])
            self.assertEqual(parent_provider.store.read('checkpoint',parent_key),original)

    def test_metadata_count_preserved_without_furniture_expansion(self):
        raw=grouped(2)
        raw['entities'].append(dict(id='markings',kind='aisle',role='free_space',category='marking',
            description='Two floor markings',confidence=.9,region='middle_centre',spatial_confidence=.8,instance_count=2))
        observation=ObservationArtifact.from_mapping(raw)
        effective,trace=expand_observation_instances(observation)
        self.assertEqual(observation.to_dict(),raw)
        self.assertEqual(trace['effective_object_count'],2)
        self.assertEqual(len(effective.entities),3)
        self.assertEqual(trace['metadata_counts'],[dict(observation_id='markings',role='free_space',instance_count=2)])
        self.assertEqual(effective.entities[-1]['id'],'markings')
        for count in (0,-1,True,1.5):
            bad=deepcopy(raw);bad['entities'][-1]['instance_count']=count
            with self.subTest(count=count),self.assertRaises(InvalidProviderResponseError) as raised:
                ObservationArtifact.from_mapping(bad)
            self.assertEqual(raised.exception.contract_report['issues'][0]['path'],'$.entities[1].instance_count')

    def test_initial_observer_failure_saves_record_but_no_draft(self):
        raw,_,_=many_objects(1)
        raw['entities'][0]['instance_count']=0
        exhausted=ChatCompletion('fixture',f.OBSERVER_MODEL,'','length',{'prompt_tokens':5,'completion_tokens':40000})
        transport=f.FixtureTransport([raw,exhausted])
        request=replace(f.text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),))
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,folder)
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            progress=provider.diagnostic_for(request.request_id)['inventory_progress']
            self.assertTrue(progress['checkpoint_saved']);self.assertFalse(progress['draft_saved'])
            self.assertFalse(progress['observation_saved']);self.assertFalse(progress['inventory_planned'])
        feedback=json.loads(transport.bodies[1]['messages'][-1]['content'][-1]['text'])
        self.assertEqual(feedback['validation']['issues'][0]['path'],'$.entities[0].instance_count')

    def test_bare_validation_rule_is_present_in_repair_feedback(self):
        raw,structure,batches=many_objects(1)
        bad=deepcopy(raw);bad['entities'][0]['confidence']=2
        transport=f.FixtureTransport([bad,raw,structure,*batches])
        request=replace(f.text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),))
        with TemporaryDirectory() as folder:
            asyncio.run(GenerationService(self.provider(transport,folder),f.config(timeout_s=300),plan_version='2.2').generate(request))
        feedback=json.loads(transport.bodies[1]['messages'][-1]['content'][-1]['text'])
        self.assertTrue(feedback['validation']['issues'])
        self.assertIn('content is invalid',feedback['validation']['issues'][0]['detail'])

    def test_partial_projection_keeps_whole_inventory_and_full_compile_rejects_it(self):
        raw,structure,batches=many_objects(12)
        observation,_=expand_observation_instances(ObservationArtifact.from_mapping(raw))
        request=replace(f.text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),))
        draft=checked_batch(batches[0],scene_draft(checked_structure(structure,request,observation,bound=True)),list(batches[0]))
        original=deepcopy(draft)
        plan,_,progress=compile_generation_preview(draft,observation,request)
        self.assertEqual(draft,original);self.assertEqual(len(draft['inventory']),12)
        self.assertEqual(progress['rendered_count'],6);self.assertEqual(progress['pending_count'],6)
        self.assertFalse(progress['physical_authority']);self.assertTrue(progress['preview_only'])
        with self.assertRaisesRegex(InvalidProviderResponseError,'SEMANTIC_DRAFT_INCOMPLETE'):
            compile_scene(draft,observation,request)
        execute_site_tool_plan(SiteToolPlan.from_dict(plan),source='photo',source_ref='a'*64)

    def test_child_waits_for_parent_without_erasing_parameterized_child(self):
        request=f.text_request('Create a bed and a bag in an estimated room')
        inventory=f.structure()['inventory']+[dict(id='bag',kind='bag',source=dict(
            basis='user',observation_ids=[],user_quote='a bag'))]
        draft=scene_draft(checked_structure({**f.structure(),'inventory':inventory},request,f.empty_observation()))
        bag=dict(region='middle_centre',yaw_deg=0,model_id='common.bag',dimensions_m=[.3,.25,.3],
            variant='standard',finish='catalog_default',placement=dict(relation='surface',parent_id='bed',
                part='mattress',anchor='centre',elevation_m=None))
        draft=checked_batch({'bag':bag},draft,['bag'])
        before=deepcopy(draft)
        plan,_,progress=compile_generation_preview(draft,f.empty_observation(),request)
        self.assertEqual(draft,before);self.assertEqual(progress['rendered_count'],0)
        self.assertEqual(progress['pending_count'],2)
        self.assertEqual([call['tool'] for call in plan['calls']],['create_floor','create_wall','create_wall','create_wall'])


    def test_preview_updates_by_batch_and_retains_last_on_output_stop(self):
        raw,structure,batches=many_objects(12)
        exhausted=ChatCompletion('fixture',f.PLANNER_MODEL,'','length',{'prompt_tokens':5,'completion_tokens':40000})
        port=PreviewPort();transport=f.FixtureTransport([raw,structure,batches[0],exhausted])
        request=replace(f.text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),),render_review_port=port)
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,folder)
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(len(port.plans),3)  # Early shell, inventory shell, then six before stop.
        self.assertEqual(len(cp['draft']['inventory']),12);self.assertEqual(len(cp['draft']['objects']),6)
        self.assertEqual(cp['generation_preview']['rendered_count'],6)
        self.assertEqual(cp['generation_preview']['pending_count'],6)
        self.assertIsNotNone(cp['preview_plan']);self.assertIsNone(cp['compiled_plan'])
        self.assertEqual(cp['Build'],'PREVIEW_ONLY')
        self.assertEqual(cp['Run'],'NOT_RUN');self.assertEqual(len(transport.bodies),6)
        self.assertEqual([b['response_format']['json_schema']['name'] for b in transport.bodies[:3]],
            ['twinpulse_room_observation','twinpulse_semantic_room','twinpulse_image_observation'])
        self.assertIsNotNone(cp['structure_observation'])

    def test_detailed_structure_revises_provisional_shell_without_duplicate_inventory(self):
        raw,structure,batches=many_objects(6)
        class DifferentEarlyShell(f.FixtureTransport):
            async def complete(self,body,token,config):
                result=await super().complete(body,token,config)
                if body['response_format']['json_schema']['name']=='twinpulse_semantic_room':
                    seed=json.loads(result.content)
                    seed['room']['width_m']-=2
                    return replace(result,content=json.dumps(seed))
                return result
        port=PreviewPort();transport=DifferentEarlyShell([raw,structure,*batches])
        request=replace(f.text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),),render_review_port=port)
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,folder)
            asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(port.plans[0]['calls'][0]['arguments']['size_m'][0],structure['room']['width_m']-2)
        self.assertEqual(cp['draft']['room'],structure['room'])
        self.assertEqual(len(cp['draft']['inventory']),6)
        self.assertEqual(len({r['id'] for r in cp['draft']['inventory']}),6)
        self.assertEqual(cp['generation_preview']['rendered_count'],6)
        self.assertEqual(cp['generation_preview']['pending_count'],0)

    def test_shape_invalid_slot_preserves_other_slots_before_repair_output_stop(self):
        raw,structure,batches=many_objects(12)
        broken=deepcopy(batches[0]);identity=next(iter(broken));broken[identity]['variant']='not-a-library-variant'
        exhausted=ChatCompletion('fixture',f.PLANNER_MODEL,'','length',{'prompt_tokens':5,'completion_tokens':40000})
        port=PreviewPort();transport=f.FixtureTransport([raw,structure,broken,exhausted])
        request=replace(f.text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),),render_review_port=port)
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,folder)
            with self.assertRaises(InvalidProviderResponseError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(len(cp['draft']['inventory']),12);self.assertEqual(len(cp['draft']['objects']),5)
        self.assertEqual(cp['generation_preview']['rendered_count'],5)
        self.assertEqual(cp['generation_preview']['pending_count'],7)
        self.assertEqual(cp['pending_parameter_candidates'][identity],broken[identity])
        self.assertIsNone(cp['compiled_plan']);self.assertEqual(cp['Run'],'NOT_RUN')

    def test_shape_repair_success_clears_pending_and_preserves_exact_completed_draft(self):
        raw,structure,batches=many_objects(12)
        broken=deepcopy(batches[0]);identity=next(iter(broken));broken[identity]['variant']='not-a-library-variant'
        patch=dict(base_revision=canonical_sha256(broken),operations=[dict(op='set',id=identity,value=batches[0][identity])])
        port=PreviewPort();transport=f.FixtureTransport([raw,structure,broken,patch,batches[1]])
        request=replace(f.text_request(),images=(ImageInput('fixture.jpg','image/jpeg',b'fixture'),),render_review_port=port)
        with TemporaryDirectory() as folder:
            provider=self.provider(transport,folder)
            asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        self.assertEqual(cp['pending_parameter_candidates'],{})
        self.assertEqual(cp['draft']['objects'][identity],batches[0][identity])
        self.assertEqual(cp['generation_preview']['rendered_count'],12)
        self.assertEqual(cp['generation_preview']['pending_count'],0)
        self.assertEqual(cp['budget']['repairs'],1)


if __name__=='__main__':unittest.main()
