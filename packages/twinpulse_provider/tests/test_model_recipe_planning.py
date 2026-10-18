# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary request-local recipe integration, not model acceptance."""
from copy import deepcopy
import unittest
from twinpulse_core.model_recipe import RECIPE_VERSION,INTERPRETER_VERSION,recipe_model_id
from twinpulse_provider.contracts import GenerationRequest
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.semantic_scene import checked_structure,scene_draft,checked_batch,compile_scene
from twinpulse_provider.model_recipe_planning import checked_resolution
from twinpulse_provider.scene_contract import SceneContractError
from twinpulse_provider.repair_scope import normalize_delta,DELTA_REVISION
from twinpulse_provider.semantic_scene import revision,patch_candidate


def plinth_recipe():
    return dict(schema_version=RECIPE_VERSION,interpreter_version=INTERPRETER_VERSION,title='Reusable low plinth',family='common',kind='storage',
        parameters=[dict(name=k,type='number',minimum=.3,maximum=2.,default=v) for k,v in [('width',1.),('depth',.6),('height',.4)]],
        parts=[dict(id='platform',center=[0,0,dict(op='mul',args=['height',.5])],size=['width','depth','height'],
            material='wood',support_top=False,repeat=None)])


class RecipePlanningTests(unittest.TestCase):
    def test_missing_definition_reads_real_child_demand_and_binds_only_explicit_parts(self):
        from types import SimpleNamespace
        from twinpulse_provider.model_recipe_planning import definition_context,checked_definition
        from test_recipe_authoring import table
        candidate=deepcopy(self.draft)
        for identity,parent in [('box','plinth'),('nested','box'),('unrelated',None)]:
            candidate['inventory'].append(dict(id=identity,kind='box',source=dict(
                basis='inferred',observation_ids=[identity+'_seen'],user_quote=None)))
            candidate['objects'][identity]=dict(region='middle_centre',yaw_deg=0,model_id='common.box',
                dimensions_m=[.2,.1,.1],variant='standard',finish='catalog_default',placement=dict(
                    relation='surface' if parent else 'floor',parent_id=parent,part='body' if parent else None,
                    anchor='centre',elevation_m=None))
        before=deepcopy(candidate)
        context=definition_context(candidate,SimpleNamespace(relations=[]),'plinth')
        self.assertEqual(context['source_target_ids'],['box','nested','plinth'])
        self.assertEqual(context['pending_object_ids'],['plinth'])
        self.assertEqual(context['current_support_demands'][0]['dimensions_m'],[.2,.1,.1])
        self.assertEqual(candidate,before)
        recipe,bindings=checked_definition(dict(recipe=table(),support_bindings={'box':'lower'}),
            'storage','plinth',['box'])
        self.assertEqual(bindings,{'box':'lower'})
        self.assertEqual(recipe['interpreter_version'],INTERPRETER_VERSION)
        for part in ('body','null'):
            with self.assertRaises(SceneContractError):checked_definition(
                dict(recipe=table(),support_bindings={'box':part}),'storage','plinth',['box'])
        self.assertEqual(candidate,before)  # No body -> shelf substitution.

    def test_capability_decline_keeps_shared_budget_and_tries_semantic_support(self):
        import asyncio
        from dataclasses import replace
        from twinpulse_provider import GenerationService
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        from twinpulse_provider.generation_policy import GenerationPolicy
        from test_budgeted_generation import FixtureTransport,config,OBSERVER_MODEL,PLANNER_MODEL
        class Library:
            def snapshots(self):return {}
            def register(self,*args,**kwargs):raise AssertionError('No new recipe')
        class Dynamic(FixtureTransport):
            async def complete(self,body,token,cfg):
                if self.responses and callable(self.responses[0]):self.responses[0]=self.responses[0](body)
                return await super().complete(body,token,cfg)
        request=replace(GenerationRequest('declined-model','Create a storage plinth and a box in a room'),model_library_port=Library())
        structure=dict(summary='Plinth and box',room=dict(width_m=4,length_m=5,height_m=2.8),inventory=[
            dict(id='plinth',kind='storage',evidence_ref='text:0'),dict(id='box',kind='box',evidence_ref='text:0')])
        floor=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None)
        objects=dict(plinth=dict(region='middle_centre',yaw_deg=0,model_id='common.storage',dimensions_m=[.8,.445,.9],
            variant='standard',finish='natural',placement=floor),
            box=dict(region='middle_centre',yaw_deg=0,model_id='common.box',dimensions_m=[.6,.55,.2],variant='standard',
                finish='catalog_default',placement=dict(relation='surface',parent_id='plinth',part='body',anchor='centre',elevation_m=None)))
        def decline(body):
            schema=body['response_format']['json_schema']['schema']['properties']['base_revision']
            return dict(base_revision=schema.get('const',(schema.get('enum') or [None])[0]),
                replacements={'plinth':None})
        def semantic(body):
            schema=body['response_format']['json_schema']['schema']['properties']
            base=schema['base_revision']
            return dict(patch_version=DELTA_REVISION,base_revision=base.get('const',(base.get('enum') or [None])[0]),room=None,
                changes={i:dict(dimensions_m=[1.2,.8,.9]) if i=='plinth' else None
                    for i in schema['changes']['properties']})
        transport=Dynamic([structure,{'plinth':'common.storage'},objects,decline,semantic])
        pipeline=BudgetedPipeline(transport,policy=GenerationPolicy(),observer_model_id=OBSERVER_MODEL,planner_model_id=PLANNER_MODEL,
            site_plan_version='2.2')
        result=asyncio.run(GenerationService(pipeline,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(len(transport.bodies),5);self.assertEqual(pipeline._budget.repairs,2)
        self.assertTrue(result.provider_provenance['checks_complete'])
        self.assertEqual(pipeline._diagnostic['capability_decline']['progressed'],False)
        self.assertEqual(pipeline._diagnostic['attempts'][3]['validation'],'declined')

    def test_capability_joint_surface_binding_is_explicit_frozen_and_cycle_checked(self):
        from twinpulse_provider.model_capability_repair import checked_capability,capability_signature
        from test_recipe_authoring import table
        request=GenerationRequest('nested-cover',self.request.prompt+' with a surface cover and a box')
        floor=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None)
        candidate=checked_batch({'plinth':dict(region='middle_centre',yaw_deg=0,model_id='common.storage',
            dimensions_m=[1.2,.8,.4],variant='standard',finish='natural',placement=floor)},self.draft,['plinth'])
        for identity,kind,model,dims in [('cover','surface_covering','common.surface_covering',[1.,.6,.01]),
                                       ('prop','box','common.box',[.1,.1,.1])]:
            candidate['inventory'].append(dict(id=identity,kind=kind,source=dict(
                basis='user',observation_ids=[],user_quote=request.prompt)))
            candidate['objects'][identity]=dict(region='middle_centre',yaw_deg=0,model_id=model,
                dimensions_m=dims,variant='standard',finish='catalog_default',placement=dict(
                    relation='surface',parent_id='plinth',part='body',anchor='centre',elevation_m=None))
        diagnosis={'issues':[dict(code='PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE',target_ids=['cover'],
            actual=dict(reason='SURFACE_CAPACITY_EXCEEDED'),expected=dict(parent_id='plinth',part='body'))]}
        raw=table()
        replacement=dict(model={'recipe':raw},dimensions_m=[1.2,.8,1.4],variant='standard',finish='recipe_materials',
            recipe_parameters={'width':1.2,'depth':.8,'height':1.4},support_bindings=dict(
                cover='lower',prop=dict(parent_id='cover',part='top',anchor='centre')))
        value=dict(base_revision=revision(candidate),replacements={'plinth':replacement})
        result,_=checked_capability(value,candidate,diagnosis,{})
        self.assertEqual(result['objects']['prop']['placement']['parent_id'],'cover')
        self.assertEqual(result['inventory'],candidate['inventory'])
        self.assertEqual(result['objects']['prop']['dimensions_m'],[.1,.1,.1])
        _,checks=compile_scene(result,self.observation,request)
        self.assertTrue(checks['checks_complete'])
        with_wall=deepcopy(candidate)
        with_wall['inventory'].append(dict(id='poster',kind='wall_fixture',source=dict(
            basis='user',observation_ids=[],user_quote=request.prompt)))
        with_wall['objects']['poster']=dict(region='rear_centre',yaw_deg=0,model_id='common.wall_fixture',
            dimensions_m=[.2,.02,.2],variant='standard',finish='catalog_default',recipe_parameters=None,placement=dict(
                relation='wall',parent_id='rear_wall',part=None,anchor='centre',elevation_m=1.5))
        wall_value=deepcopy(value);wall_value['base_revision']=revision(with_wall)
        wall_result,_=checked_capability(wall_value,with_wall,diagnosis,{})
        self.assertEqual(wall_result['objects']['poster'],with_wall['objects']['poster'])
        for bindings in [dict(cover='null',prop='lower'),
                         dict(cover=dict(parent_id='prop',part='top',anchor='centre'),
                              prop=dict(parent_id='cover',part='top',anchor='centre')),
                         dict(cover='lower',prop=dict(parent_id='unrelated',part='top',anchor='centre'))]:
            invalid=deepcopy(value);invalid['replacements']['plinth']['support_bindings']=bindings
            with self.assertRaises(SceneContractError):checked_capability(invalid,candidate,diagnosis,{})
        nested=deepcopy(candidate);nested['objects']['prop']['placement']['parent_id']='cover'
        altered=deepcopy(nested);altered['objects']['prop']['dimensions_m'][0]=.12
        self.assertNotEqual(capability_signature(nested,diagnosis),capability_signature(altered,diagnosis))
        unknown=deepcopy(candidate);unknown['inventory'][-2]['kind']='unknown'
        unknown['objects']['cover']['model_id']='common.unknown'
        invalid=deepcopy(value);invalid['base_revision']=revision(unknown)
        with self.assertRaises(SceneContractError):checked_capability(invalid,unknown,diagnosis,{})

    def test_custom_warehouse_recipe_keeps_recipe_geometry_not_builtin_factory(self):
        recipe=plinth_recipe();recipe['kind']='rack'
        draft=deepcopy(self.draft);draft['inventory'][0]['kind']='rack'
        draft,_=checked_resolution({'plinth':{'recipe':recipe}},draft,{})
        value=dict(region='middle_centre',yaw_deg=90,model_id=recipe_model_id(recipe),dimensions_m=[1.,.6,.4],
            variant='standard',finish='recipe_materials',recipe_parameters={'width':1.,'depth':.6,'height':.4},
            placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
        draft=checked_batch({'plinth':value},draft,['plinth'])
        payload,provenance=compile_scene(draft,self.observation,self.request)
        self.assertEqual(next(c for c in payload['calls'] if c['arguments']['id']=='plinth')['tool'],'place_model_recipe')
        self.assertTrue(provenance['checks_complete'])

    def test_first_partial_support_enters_capability_repair_in_the_same_budget(self):
        import asyncio,json
        from dataclasses import replace
        from twinpulse_provider import GenerationService
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        from twinpulse_provider.generation_policy import GenerationPolicy
        from test_budgeted_generation import FixtureTransport,config,OBSERVER_MODEL,PLANNER_MODEL
        class Library:
            def snapshots(self):return {}
            def register(self,*args,**kwargs):raise AssertionError('Builtin reuse must not register a new recipe')
        class Dynamic(FixtureTransport):
            async def complete(self,body,token,cfg):
                if self.responses and callable(self.responses[0]):self.responses[0]=self.responses[0](body)
                return await super().complete(body,token,cfg)
        request=replace(GenerationRequest('first-partial','Create a storage plinth and a box in a room'),model_library_port=Library())
        structure=dict(summary='Plinth and box',room=dict(width_m=4,length_m=5,height_m=2.8),inventory=[
            dict(id='plinth',kind='storage',evidence_ref='text:0'),dict(id='box',kind='box',evidence_ref='text:0')])
        floor=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None)
        objects=dict(plinth=dict(region='middle_centre',yaw_deg=0,model_id='common.storage',dimensions_m=[.8,.445,.9],
            variant='standard',finish='natural',placement=floor),
            box=dict(region='middle_centre',yaw_deg=0,model_id='common.box',dimensions_m=[.6,.55,.2],variant='standard',
                finish='catalog_default',placement=dict(relation='surface',parent_id='plinth',part='body',anchor='centre',elevation_m=None)))
        def response(body):
            schema=body['response_format']['json_schema']['schema'];props=schema['properties']
            rev=props['base_revision'].get('const',(props['base_revision'].get('enum') or [None])[0])
            return dict(base_revision=rev,replacements={'plinth':dict(model={'model_id':'common.storage'},
                dimensions_m=[1.2,.8,.9],variant='standard',finish='natural',recipe_parameters=None,support_bindings={'box':'body'})})
        transport=Dynamic([structure,{'plinth':'common.storage'},objects,response])
        pipeline=BudgetedPipeline(transport,policy=GenerationPolicy(),observer_model_id=OBSERVER_MODEL,planner_model_id=PLANNER_MODEL,
            site_plan_version='2.2')
        result=asyncio.run(GenerationService(pipeline,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(len(transport.bodies),4);self.assertEqual(pipeline._budget.repairs,1)
        self.assertTrue(result.provider_provenance['checks_complete'])
        self.assertEqual(next(c.arguments['dimensions_m'] for c in result.plan.calls if c.call_id=='obj_plinth'),[1.2,.8,.9])
        # A complete but invalid model proposal stalls inside content_stage,
        # before the outer geometry repair_result branch. Retain the unchanged
        # checked subset, not that proposal and not a whole-inventory PASS.
        invalid=Dynamic([structure,{'plinth':'common.storage'},objects,{'invalid':True},{'invalid':True},{'invalid':True}])
        stopped=BudgetedPipeline(invalid,policy=GenerationPolicy(),observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2')
        partial=asyncio.run(GenerationService(stopped,config(timeout_s=300),plan_version='2.2').generate(request))
        refinement=partial.provider_provenance['draft_refinement']
        self.assertEqual(refinement['stop_reason'],'REPAIR_STALLED')
        self.assertEqual(refinement['acceptance'],'MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE')
        self.assertEqual(len(invalid.bodies),5);self.assertEqual(stopped._budget.repairs,2)
        self.assertEqual(stopped._budget.no_progress,2)
        self.assertEqual(partial.provider_provenance['progressive_twin']['unresolved'][0]['id'],'box')
        self.assertEqual(next(c.arguments['dimensions_m'] for c in partial.plan.calls if c.call_id=='obj_plinth'),[.8,.445,.9])
        self.assertEqual(refinement['quality_review']['photo_comparison'],'not_run')
        def semantic_after_rejection(body):
            props=body['response_format']['json_schema']['schema']['properties']
            base=props['base_revision']
            return dict(patch_version=DELTA_REVISION,base_revision=base.get('const',(base.get('enum') or [None])[0]),
                room=None,changes={i:dict(dimensions_m=[1.2,.8,.9]) if i=='plinth' else None
                    for i in props['changes']['properties']})
        recovery=Dynamic([structure,{'plinth':'common.storage'},objects,{'invalid':True},semantic_after_rejection])
        recovered=BudgetedPipeline(recovery,policy=GenerationPolicy(),observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2')
        result=asyncio.run(GenerationService(recovered,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertTrue(result.provider_provenance['checks_complete'])
        self.assertEqual(len(recovery.bodies),5);self.assertEqual(recovered._budget.repairs,2)
        self.assertEqual(recovered._diagnostic['attempts'][3]['validation'],'failed')
        self.assertEqual(recovered._diagnostic['capability_decline']['proposal_outcome'],'rejected')

    def test_small_discovery_and_one_definition_contract(self):
        from twinpulse_provider.model_recipe_planning import selection_schema,checked_selection,checked_single_recipe
        schema=selection_schema(self.draft,{},['plinth'])
        import json
        self.assertLess(len(json.dumps(schema)),400)
        self.assertEqual(checked_selection({'plinth':'create_recipe'},self.draft,{},['plinth']),{'plinth':'create_recipe'})
        self.assertEqual(checked_single_recipe(plinth_recipe(),'storage','plinth'),plinth_recipe())
        with self.assertRaises(SceneContractError):checked_selection({'plinth':'local.missing'},self.draft,{},['plinth'])

    def test_capability_repair_preserves_identity_and_is_not_a_general_model_swap(self):
        from twinpulse_provider.model_capability_repair import capability_targets,checked_capability,capability_signature
        value=dict(region='middle_centre',yaw_deg=0,model_id='common.storage',dimensions_m=[.8,.445,.9],
            variant='standard',finish='natural',placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
        candidate=checked_batch({'plinth':value},self.draft,['plinth'])
        request=GenerationRequest('capability-case',self.request.prompt+' with a box')
        candidate['inventory'].append(dict(id='box',kind='box',source=dict(basis='user',observation_ids=[],user_quote=request.prompt)))
        candidate['objects']['box']=dict(region='middle_centre',yaw_deg=0,model_id='common.box',dimensions_m=[.2,.2,.2],
            variant='standard',finish='catalog_default',placement=dict(relation='surface',parent_id='plinth',part='body',anchor='centre',elevation_m=None))
        diagnosis={'issues':[dict(code='PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE',target_ids=['box'],
            actual=dict(reason='SURFACE_CAPACITY_EXCEEDED'),expected=dict(parent_id='plinth',part='body'))]}
        self.assertEqual(capability_targets(candidate,diagnosis),{'plinth':['box']})
        timed=deepcopy(diagnosis);timed['issues'][0]['expected']['bounded_search']={'elapsed_s':1.234,'nodes':81}
        self.assertEqual(capability_signature(candidate,diagnosis),capability_signature(candidate,timed))
        altered=deepcopy(candidate);altered['objects']['box']['dimensions_m']=[.25,.2,.2]
        self.assertNotEqual(capability_signature(candidate,diagnosis),capability_signature(altered,diagnosis))
        draped=deepcopy(candidate);draped['objects']['drape']=deepcopy(candidate['objects']['box'])
        draped['objects']['drape']['placement']['relation']='drape'
        self.assertEqual(capability_targets(draped,diagnosis),{})
        recipe=plinth_recipe();recipe['parameters'][2]['maximum']=.4
        recipe['parts'][0]['support_top']=True
        recipe['parts'][0]['size'][2]=.025
        recipe['parts'][0]['center'][2]=dict(op='sub',args=['height',.0125])
        recipe['parts'].append(dict(id='foot',center=[0,0,dict(op='mul',args=[dict(op='sub',args=['height',.025]),.5])],
            size=[.1,.1,dict(op='sub',args=['height',.025])],material='wood',support_top=False,repeat=None))
        replacement=dict(model={'recipe':recipe},dimensions_m=[1.,.6,.4],variant='standard',finish='recipe_materials',
            recipe_parameters={'width':1.,'depth':.6,'height':.4},support_bindings={'box':'platform'})
        response=dict(base_revision=revision(candidate),replacements={'plinth':replacement})
        result,created=checked_capability(response,candidate,diagnosis,{})
        wrong_finish=deepcopy(response);wrong_finish['replacements']['plinth']['finish']='white'
        with self.assertRaises(SceneContractError):checked_capability(wrong_finish,candidate,diagnosis,{})
        from twinpulse_provider.model_capability_repair import capability_prompt_context
        expanded=deepcopy(candidate)
        expanded['objects']['nested']=deepcopy(expanded['objects']['box'])
        expanded['objects']['nested']['placement']['parent_id']='box'
        expanded['inventory'].append(dict(expanded['inventory'][-1],id='nested'))
        expanded['objects']['unrelated']=deepcopy(value)
        expanded['inventory'].append(dict(expanded['inventory'][0],id='unrelated'))
        repeated=deepcopy(diagnosis);options=[dict(parent_id='plinth',part='body',width_m=.8)]
        repeated['issues'][0]['expected']['support_options']=options
        repeated['issues'].append(deepcopy(repeated['issues'][0]))
        before=deepcopy(expanded)
        compact=capability_prompt_context(expanded,repeated,{})
        self.assertEqual(expanded,before)
        self.assertEqual(set(compact['candidate']['objects']),{'plinth','box','nested'})
        self.assertEqual(len(compact['support_options_tables']),1)
        self.assertTrue(all(m['kind']=='storage' for m in compact['available_models']))
        def inflate(v):
            if isinstance(v,list):return [inflate(i) for i in v]
            if not isinstance(v,dict):return v
            return {('support_options' if k=='support_options_ref' else k):
                (deepcopy(compact['support_options_tables'][i]) if k=='support_options_ref' else inflate(i))
                for k,i in v.items()}
        self.assertEqual(inflate(compact['validation']),repeated)
        self.assertEqual(compact['base_revision'],revision(expanded))
        self.assertEqual(result['inventory'],candidate['inventory']);self.assertEqual(result['room'],candidate['room'])
        self.assertEqual(result['objects']['box']['dimensions_m'],candidate['objects']['box']['dimensions_m'])
        self.assertEqual(result['objects']['box']['placement']['part'],'platform')
        self.assertEqual(result['objects']['plinth']['region'],candidate['objects']['plinth']['region'])
        self.assertEqual(set(created),{recipe_model_id(recipe)})
        payload,checks=compile_scene(result,self.observation,request)
        self.assertTrue(checks['checks_complete'])
        self.assertEqual(len([c for c in payload['calls'] if c['call_id'].startswith('obj_')]),2)
        with self.assertRaisesRegex(SceneContractError,'NO_CHANGE'):
            checked_capability(dict(base_revision=revision(candidate),replacements={'plinth':None}),candidate,diagnosis,
                {recipe_model_id(recipe):recipe})
        with self.assertRaises(SceneContractError):checked_capability(dict(response,base_revision='f'*64),candidate,diagnosis,{})
        foreign=deepcopy(response);foreign['replacements']['plinth']['region']='rear_left'
        with self.assertRaises(SceneContractError):checked_capability(foreign,candidate,diagnosis,{})
        self.assertEqual(capability_targets(candidate,{'issues':[dict(code='PHOTO_OBSERVED_REGION_CONTRADICTION')]}),{})

    def test_model_resolution_uses_configured_planner_and_rejects_image_leakage(self):
        import asyncio
        from dataclasses import replace
        from test_nebius_pipeline import config,OBSERVER_MODEL
        from twinpulse_provider import CancellationToken,ProviderConfigurationError
        from twinpulse_provider.stage_transport import ConfiguredStageTransport
        class Inner:
            calls=[]
            async def complete(self,body,token,selected):
                self.calls.append(selected.model_id)
                return 'routed'
        inner=Inner();configs={'observer':replace(config(),model_id=OBSERVER_MODEL),'planner':config()}
        transport=ConfiguredStageTransport({'observer':inner,'planner':inner},configs,
            {'observer':'nebius','planner':'nebius'},{'observer':'low','planner':'low'})
        body=dict(model=configs['planner'].model_id,messages=[dict(role='system',content='Return a model resolution'),dict(role='user',content='A reusable cabinet')],
            max_tokens=100,response_format={'type':'json_schema','json_schema':dict(name='twinpulse_model_resolution',
                schema={'type':'object','properties':{}},strict=True)})
        self.assertEqual(asyncio.run(transport.complete(body,CancellationToken(),configs['planner'])),'routed')
        body['messages'][1]['content']=[dict(type='image_url',image_url={'url':'data:image/jpeg;base64,eA=='})]
        with self.assertRaisesRegex(ProviderConfigurationError,'Images cannot'):
            asyncio.run(transport.complete(body,CancellationToken(),configs['planner']))
        self.assertEqual(inner.calls,[configs['planner'].model_id])

    def setUp(self):
        self.request=GenerationRequest('recipe-supplementary','A storage plinth in a room')
        self.observation=ObservationArtifact.from_mapping(dict(schema_version='1.0',summary='Text only',entities=[],relations=[],dimensions=[],ambiguities=[]))
        structure=checked_structure(dict(summary='Room with plinth',room=dict(width_m=4,length_m=5,height_m=2.8),
            inventory=[dict(id='plinth',kind='storage',source=dict(basis='user',observation_ids=[],user_quote=self.request.prompt))]),
            self.request,self.observation)
        self.draft=scene_draft(structure)

    def test_creation_snapshot_and_normal_compiler(self):
        recipe=plinth_recipe();draft,created=checked_resolution({'plinth':{'recipe':recipe}},self.draft,{})
        model=recipe_model_id(recipe);self.assertEqual(created,[model])
        value=dict(region='middle_centre',yaw_deg=90,model_id=model,dimensions_m=[1.,.6,.4],
            variant='standard',finish='recipe_materials',recipe_parameters={'width':1.,'depth':.6,'height':.4},
            placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
        draft=checked_batch({'plinth':value},draft,['plinth'])
        payload,provenance=compile_scene(draft,self.observation,self.request)
        call=next(c for c in payload['calls'] if c['tool']=='place_model_recipe')
        self.assertEqual(call['arguments']['recipe'],recipe)
        self.assertTrue(provenance['checks_complete'])
        changed=deepcopy(recipe);changed['title']='Replacement version'
        self.assertNotEqual(recipe_model_id(changed),model)
        again,_=compile_scene(draft,self.observation,self.request)
        self.assertEqual(payload,again)

    def test_reuse_and_no_new_definition(self):
        recipe=plinth_recipe();model=recipe_model_id(recipe)
        draft,created=checked_resolution({'plinth':{'model_id':model}},self.draft,{model:recipe})
        self.assertEqual(created,[]);self.assertTrue(draft['model_resolution_done'])

    def test_recipe_variant_and_geometry_progress_bind_exact_snapshot(self):
        from twinpulse_provider.generation_policy import ProgressTracker,diagnostic_blockers
        from twinpulse_provider.semantic_scene import compiler_diagnosis
        recipe=plinth_recipe();draft,_=checked_resolution({'plinth':{'recipe':recipe}},self.draft,{})
        value=dict(region='middle_centre',yaw_deg=0,model_id=recipe_model_id(recipe),dimensions_m=[1.,.6,.4],
            variant='open',finish='recipe_materials',recipe_parameters={'width':1.,'depth':.6,'height':.4},
            placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
        with self.assertRaises(SceneContractError):checked_batch({'plinth':value},draft,['plinth'])
        value['variant']='standard';draft=checked_batch({'plinth':value},draft,['plinth'])
        draft['room']['width_m']=.5
        try:compile_scene(draft,self.observation,self.request)
        except ValueError as error:diagnosis=compiler_diagnosis(error,draft,self.request)
        else:self.fail('Narrow room must still fail the original floor constraint')
        tracker=ProgressTracker();tracker.observe(draft,diagnostic_blockers(diagnosis,''),diagnosis)
        self.assertNotEqual(tracker.decision,'evidence_insufficient')
        changed=deepcopy(draft);changed['model_recipes'][recipe_model_id(recipe)]['title']='Foreign snapshot'
        stale=ProgressTracker();stale.observe(changed,diagnostic_blockers(diagnosis,''),diagnosis)
        self.assertEqual(stale.decision,'evidence_insufficient')

    def test_saved_variant_correction_is_exact_and_cannot_migrate_geometry(self):
        from twinpulse_provider.model_recipe_planning import restored_parameter_contract,checked_restored_parameters
        recipe=plinth_recipe();draft,_=checked_resolution({'plinth':{'recipe':recipe}},self.draft,{})
        draft['objects']['plinth']=dict(region='middle_centre',yaw_deg=0,model_id=recipe_model_id(recipe),
            dimensions_m=[1.,.6,.4],variant='open',finish='recipe_materials',
            recipe_parameters={'width':1.,'depth':.6,'height':.4},
            placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
        with self.assertRaises(SceneContractError) as caught:
            checked_batch(draft['objects'],{**draft,'objects':{}},['plinth'])
        schema=restored_parameter_contract(draft,caught.exception)
        value=dict(base_revision=revision(draft),changes={'plinth':{'variant':'standard'}})
        corrected=checked_restored_parameters(value,draft,schema)
        expected=deepcopy(draft);expected['objects']['plinth']['variant']='standard'
        self.assertEqual(corrected,expected)
        self.assertEqual(draft['objects']['plinth']['variant'],'open')
        for change in ({'variant':'standard','dimensions_m':[2.,.6,.4]}, {'model_id':'common.storage'}):
            with self.assertRaises(SceneContractError):checked_restored_parameters(dict(value,changes={'plinth':change}),draft,schema)
        with self.assertRaises(SceneContractError):checked_restored_parameters(dict(value,base_revision='0'*64),draft,schema)
        corrupted=deepcopy(draft);corrupted['model_recipes'][recipe_model_id(recipe)]['title']='Tampered'
        with self.assertRaisesRegex(ValueError,'BINDING_MISMATCH'):restored_parameter_contract(corrupted,caught.exception)
        with self.assertRaises(SceneContractError):checked_resolution({'plinth':{'model_id':'local.missing'}},self.draft,{})

    def test_dimensions_cannot_disagree_with_recipe(self):
        recipe=plinth_recipe();draft,_=checked_resolution({'plinth':{'recipe':recipe}},self.draft,{})
        value=dict(region='middle_centre',yaw_deg=0,model_id=recipe_model_id(recipe),dimensions_m=[2.,.6,.4],
            variant='standard',finish='recipe_materials',recipe_parameters={'width':1.,'depth':.6,'height':.4},
            placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
        draft=checked_batch({'plinth':value},draft,['plinth'])
        with self.assertRaisesRegex(ValueError,'BINDING_MISMATCH'):compile_scene(draft,self.observation,self.request)

    def test_existing_prop_uses_named_actual_recipe_surface(self):
        recipe=plinth_recipe()
        recipe['title']='Two-part stand'
        recipe['parts']=[dict(id='leg',center=[0,0,dict(op='mul',args=['height',.5])],size=[.05,.05,'height'],
            material='metal',support_top=False,repeat=None),
            dict(id='top',center=[0,0,dict(op='sub',args=['height',.01])],size=['width','depth',.02],
                material='wood',support_top=True,repeat=None)]
        draft=deepcopy(self.draft)
        draft['inventory'].append(dict(id='book',kind='tabletop_item',source=dict(basis='user',observation_ids=[],user_quote=self.request.prompt)))
        draft,_=checked_resolution({'plinth':{'recipe':recipe}},draft,{})
        parent=dict(region='middle_centre',yaw_deg=90,model_id=recipe_model_id(recipe),dimensions_m=[1.,.6,.4],
            variant='standard',finish='recipe_materials',recipe_parameters={'width':1.,'depth':.6,'height':.4},
            placement=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))
        child=dict(region='middle_centre',yaw_deg=90,model_id='common.tabletop_item',dimensions_m=[.1,.1,.08],
            variant='standard',finish='catalog_default',recipe_parameters=None,
            placement=dict(relation='surface',parent_id='plinth',part='top',anchor='centre',elevation_m=None))
        draft=checked_batch({'plinth':parent,'book':child},draft,['plinth','book'])
        payload,provenance=compile_scene(draft,self.observation,self.request)
        self.assertTrue(provenance['checks_complete'])
        self.assertEqual(next(c for c in payload['calls'] if c['arguments']['id']=='book')['arguments']['position_m'][2],.44)
        diagnosis={'issues':[{'code':'PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE','target_ids':['book'],'related_ids':['plinth']}]}
        delta=dict(patch_version=DELTA_REVISION,base_revision=revision(draft),room=None,
            changes={'book':{'dimensions_m':[.09,.09,.08]},'plinth':None})
        patch=normalize_delta(draft,delta,diagnosis)
        changed=patch_candidate(draft,patch,self.observation,self.request,repair_diagnosis=diagnosis)
        self.assertEqual(changed['objects']['book']['placement']['part'],'top')
        self.assertTrue(compile_scene(changed,self.observation,self.request)[1]['checks_complete'])
        delta['changes']['book']={}
        with self.assertRaisesRegex(SceneContractError,'NO_CHANGE'):normalize_delta(draft,delta,diagnosis)


if __name__=='__main__':unittest.main()
