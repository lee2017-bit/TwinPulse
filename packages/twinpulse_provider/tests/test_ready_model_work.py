# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary scheduler contracts; fixed replies are NOT user acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import test_budgeted_generation as f
from test_generation_preview import PreviewPort
from test_model_recipe_planning import plinth_recipe
from twinpulse_core import canonical_sha256
from twinpulse_provider import GenerationService
from twinpulse_provider.generation_policy import GenerationBudgetError, GenerationPolicy
from twinpulse_provider.generation_preview import ready_parameter_batch
from twinpulse_provider.generation_store import input_digest
from twinpulse_provider.model_recipe_planning import floor_recipe_allowed, selection_schema
from twinpulse_app.generation_scope import OrdinaryInferenceScope


class ReadyModelWorkTests(unittest.TestCase):
    def test_unknown_does_not_gain_floor_recipe_authority_from_names_or_inside(self):
        row=dict(id='floor_named',kind='unknown',source=dict(basis='inferred',observation_ids=['u'],user_quote=None))
        obs=replace(f.empty_observation(),entities=(dict(id='u',kind='unknown',role='unknown',category='unknown'),
            dict(id='floor',kind='floor',role='structure',category='floor')),
            relations=(dict(subject_id='u',object_id='floor',relation='inside'),))
        self.assertFalse(floor_recipe_allowed(row,obs))
        probe=dict(inventory=[row],objects={})
        self.assertEqual(selection_schema(probe,{},['floor_named'],obs)['properties']['floor_named']['enum'],['common.unknown'])
        grounded=replace(obs,relations=(dict(subject_id='u',object_id='floor',relation='on'),))
        self.assertTrue(floor_recipe_allowed(row,grounded))
        not_floor=replace(grounded,entities=(grounded.entities[0],dict(id='floor',kind='other',role='object',category='storage')))
        self.assertFalse(floor_recipe_allowed(row,not_floor))
        explicit=deepcopy(row);explicit['source']=dict(basis='user',observation_ids=[],user_quote='a custom plinth')
        self.assertTrue(floor_recipe_allowed(explicit,obs))

    def test_unresolved_parent_never_binds_children_to_builtin_fallback(self):
        draft=dict(inventory=[dict(id=i,kind=k,source=dict(basis='inferred',observation_ids=[i],user_quote=None))
            for i,k in [('prop','tabletop_item'),('custom','storage'),('bed','bed')]],objects={},
            model_selections={'bed':'home.bed'})
        obs=replace(f.empty_observation(),relations=(dict(subject_id='prop',object_id='custom',relation='on'),))
        self.assertEqual(ready_parameter_batch(draft,obs,6),['bed'])
        draft['objects']['bed']={};draft['model_selections']['custom']='local.example'
        self.assertEqual(ready_parameter_batch(draft,obs,6),['custom','prop'])
        self.assertEqual(len(draft['inventory']),3)

    def test_valid_parent_is_rendered_before_unrelated_definition_exhausts_budget(self):
        class Library:
            def snapshots(self):return {}
            def register(self,*args,**kwargs):raise AssertionError('Invalid definition must never register')
        request=replace(f.text_request('Create a bed and a storage plinth in a room'),model_library_port=Library())
        shape=f.wire_structure();shape['inventory'].append(dict(id='plinth',kind='storage',evidence_ref='text:0'))
        bad=plinth_recipe();bad['parts'][0]['size'][0]=0
        port=PreviewPort();transport=f.FixtureTransport([shape,{'bed':'home.bed','plinth':'create_recipe'},
            {'bed':f.bed()},bad,bad])
        policy=replace(GenerationPolicy(),max_repairs=1)
        with TemporaryDirectory() as folder:
            provider=f.BudgetedPipeline(transport,policy=policy,store_root=folder,
                observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
            with self.assertRaises(GenerationBudgetError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(
                    replace(request,render_review_port=port)))
            cp=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
        names=[b['response_format']['json_schema']['name'] for b in transport.bodies]
        self.assertLess(names.index('twinpulse_semantic_batch'),names.index('twinpulse_model_recipe'))
        self.assertEqual(set(cp['draft']['objects']),{'bed'})
        self.assertEqual(len(cp['draft']['inventory']),2)
        self.assertEqual(cp['generation_preview']['rendered_count'],1)
        self.assertTrue(any(any(c['arguments'].get('id')=='bed' for c in p['calls']) for p in port.plans))
        work=cp['draft']['model_definition_work']['plinth']
        self.assertEqual(work['state'],'validation_failed');self.assertEqual(len(work['attempt_ids']),2)
        self.assertEqual(work['last_attempt_id'],work['failure']['attempt_id'])
        self.assertIsNone(cp['compiled_plan']);self.assertEqual(cp['budget']['repairs'],1)

    def test_exhausted_terminal_cannot_resume_an_initial_definition(self):
        from twinpulse_provider import InvalidProviderResponseError
        for reason in ('REPAIR_LIMIT_REACHED','REPAIR_STALLED','REQUEST_LIMIT_REACHED','NEEDS_TIME_BUDGET'):
            with self.subTest(reason=reason),TemporaryDirectory() as folder:
                root=Path(folder);request=f.text_request(identity='terminal-parent')
                provider=f.BudgetedPipeline(f.FixtureTransport([f.wire_structure(),
                    f.ChatCompletion('limit',f.PLANNER_MODEL,'','length',{})]),policy=GenerationPolicy(),store_root=root/'store',
                    observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
                with self.assertRaises(InvalidProviderResponseError):
                    asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
                key=provider.diagnostic_for(request.request_id)['checkpoint_id']
                original=provider.store.read('checkpoint',key);parent=deepcopy(original)
                parent['budget']['stop_reason']=reason
                audit_key=canonical_sha256(dict(parent=key,reason=reason));provider.store.save('checkpoint',audit_key,parent)
                scope=OrdinaryInferenceScope('ordinary-generation:terminal-'+reason,input_digest(request),'b'*64,
                    GenerationPolicy().sha256,root/'scope.json',{},'1',12,
                    approved_checkpoint_sha256=canonical_sha256(parent))
                transport=f.FixtureTransport([])
                next_provider=f.BudgetedPipeline(transport,policy=GenerationPolicy(),store_root=root/'store',route_sha256='b'*64,
                    observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
                with self.assertRaisesRegex(GenerationBudgetError,reason):
                    asyncio.run(GenerationService(next_provider,f.config(timeout_s=300),plan_version='2.2').generate(
                        replace(request,request_id='terminal-child',inference_scope=scope,continuation_checkpoint=audit_key)))
                self.assertEqual(transport.bodies,[]);self.assertEqual(provider.store.read('checkpoint',key),original)

    def test_cancelled_failed_definition_resumes_as_repair_with_its_exact_history(self):
        from twinpulse_provider import GenerationCancelledError
        class Library:
            def snapshots(self):return {}
            def register(self,*args,**kwargs):pass
        request=replace(f.text_request('Create a bed and a storage plinth in a room',identity='work-parent'),
            model_library_port=Library(),render_review_port=PreviewPort())
        shape=f.wire_structure();shape['inventory'].append(dict(id='plinth',kind='storage',evidence_ref='text:0'))
        bad=plinth_recipe();bad['parts'][0]['size'][0]=0
        with TemporaryDirectory() as folder:
            root=Path(folder);policy=GenerationPolicy()
            provider=f.BudgetedPipeline(f.FixtureTransport([shape,{'bed':'home.bed','plinth':'create_recipe'},
                {'bed':f.bed()},bad,GenerationCancelledError('Explicit fixture cancellation')]),policy=policy,
                store_root=root/'store',observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
            with self.assertRaises(GenerationCancelledError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            key=provider.diagnostic_for(request.request_id)['checkpoint_id'];parent=provider.store.read('checkpoint',key)
            failed=parent['draft']['model_definition_work']['plinth']
            self.assertEqual(failed['state'],'validation_failed');self.assertIsNotNone(failed['failure'])
            scope=OrdinaryInferenceScope('ordinary-generation:work-resume',input_digest(request),'b'*64,policy.sha256,
                root/'scope.json',{f.PLANNER_MODEL:dict(input_per_million=1,output_per_million=1,context_tokens=40000,
                    source='fixture-only')},'1',12,approved_checkpoint_sha256=canonical_sha256(parent))
            recipe=plinth_recipe();model=f'local.{canonical_sha256(recipe)[:24]}'
            value=dict(region='rear_right',yaw_deg=0,model_id=model,dimensions_m=[1.,.6,.4],variant='standard',
                finish='recipe_materials',recipe_parameters=dict(width=1.,depth=.6,height=.4),
                placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
            transport=f.FixtureTransport([recipe,{'plinth':value}])
            child=f.BudgetedPipeline(transport,policy=policy,store_root=root/'store',route_sha256='b'*64,
                observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
            result=asyncio.run(GenerationService(child,f.config(timeout_s=300),plan_version='2.2').generate(replace(request,
                request_id='work-child',inference_scope=scope,continuation_checkpoint=key,render_review_port=PreviewPort())))
            self.assertEqual(result.provider_provenance['budget']['attempts'][0]['role'],'repair')
            self.assertIn('previous_candidate',transport.bodies[0]['messages'][-1]['content'])
            self.assertEqual(provider.store.read('checkpoint',key),parent)
            self.assertEqual(result.provider_provenance['budget']['repairs'],parent['budget']['repairs']+1)

    def test_library_registration_failure_retains_recipe_and_stops_paid_replay(self):
        from twinpulse_provider import ProviderConfigurationError
        class BrokenLibrary:
            def snapshots(self):return {}
            def register(self,*args,**kwargs):raise PermissionError('Explicit fixture storage fault')
        request=replace(f.text_request('Create a storage plinth in a room',identity='registration-fault'),
            model_library_port=BrokenLibrary())
        shape=dict(summary='Estimated room',room=dict(width_m=6,length_m=6,height_m=2.6),
            inventory=[dict(id='plinth',kind='storage',evidence_ref='text:0')])
        with TemporaryDirectory() as folder:
            root=Path(folder);transport=f.FixtureTransport([shape,{'plinth':'create_recipe'},plinth_recipe()])
            provider=f.BudgetedPipeline(transport,policy=GenerationPolicy(),store_root=root/'store',
                observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
            with self.assertRaises(ProviderConfigurationError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            parent=provider.store.read('checkpoint',provider.diagnostic_for(request.request_id)['checkpoint_id'])
            self.assertEqual(parent['budget']['stop_reason'],'MODEL_LIBRARY_REGISTRATION_FAILED')
            work=parent['draft']['model_definition_work']['plinth']
            self.assertEqual(work['state'],'registration_failed');self.assertEqual(work['validated_recipe'],plinth_recipe())
            self.assertEqual(parent['draft']['objects'],{})

    def test_definition_stage_keeps_seen_candidates_across_cancel_and_resume(self):
        from twinpulse_provider import GenerationCancelledError
        class Library:
            def snapshots(self):return {}
            def register(self,*args,**kwargs):raise AssertionError('Invalid definition cannot register')
        request=replace(f.text_request('Create a storage plinth in a room',identity='seen-parent'),model_library_port=Library())
        shape=dict(summary='Estimated room',room=dict(width_m=6,length_m=6,height_m=2.6),
            inventory=[dict(id='plinth',kind='storage',evidence_ref='text:0')])
        first=plinth_recipe();first.pop('title');second=deepcopy(first);second.pop('family')
        with TemporaryDirectory() as folder:
            root=Path(folder);policy=GenerationPolicy()
            provider=f.BudgetedPipeline(f.FixtureTransport([shape,{'plinth':'create_recipe'},first,second,
                GenerationCancelledError('Explicit fixture cancellation')]),policy=policy,store_root=root/'store',
                observer_model_id=f.OBSERVER_MODEL,planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
            with self.assertRaises(GenerationCancelledError):
                asyncio.run(GenerationService(provider,f.config(timeout_s=300),plan_version='2.2').generate(request))
            key=provider.diagnostic_for(request.request_id)['checkpoint_id'];parent=provider.store.read('checkpoint',key)
            work=parent['draft']['model_definition_work']['plinth']
            self.assertEqual(len(work['validation_progress']['seen']),2)
            self.assertEqual(parent['budget']['stalled_repairs'],1)
            scope=OrdinaryInferenceScope('ordinary-generation:seen-resume',input_digest(request),'b'*64,policy.sha256,
                root/'scope.json',{f.PLANNER_MODEL:dict(input_per_million=1,output_per_million=1,context_tokens=40000,
                    source='fixture-only')},'1',12,approved_checkpoint_sha256=canonical_sha256(parent))
            transport=f.FixtureTransport([first]);child=f.BudgetedPipeline(transport,policy=policy,
                store_root=root/'store',route_sha256='b'*64,observer_model_id=f.OBSERVER_MODEL,
                planner_model_id=f.PLANNER_MODEL,site_plan_version='2.2')
            with self.assertRaisesRegex(GenerationBudgetError,'REPAIR_STALLED'):
                asyncio.run(GenerationService(child,f.config(timeout_s=300),plan_version='2.2').generate(
                    replace(request,request_id='seen-child',inference_scope=scope,continuation_checkpoint=key)))
            self.assertEqual(child._budget.no_progress,2)
            self.assertEqual(transport.bodies[0]['response_format']['json_schema']['name'],'twinpulse_model_recipe')
            self.assertEqual(provider.store.read('checkpoint',key),parent)


if __name__=='__main__':unittest.main()
