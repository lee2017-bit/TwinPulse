# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline OpenAI strict-schema wire checks. No provider call; not model or live API acceptance.

The strict rules are OpenAI's documented Structured Outputs subset; whether the
live API accepts each wire body is unverified here.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import inspect
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from twinpulse_core.model_recipe import recipe_digest,recipe_model_id
from twinpulse_provider import CancellationToken,GenerationRequest,InvalidProviderResponseError,ProviderConfigurationError
from twinpulse_provider.contracts import ImageInput,ProviderCapabilities,ProviderConfig
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.nebius_pipeline import ChatCompletion,NebiusChatCompletionsPipelineProvider,_json_content
from twinpulse_provider.scene_contract import PROPOSAL_REVISION
from twinpulse_provider.stage_transport import (ConfiguredStageTransport,StageRoutingTransport,OPENAI_MINI_SNAPSHOT,
    explicit_json_contract,normalize_json_schema,open_map_paths,openai_map_rows,openai_observer_body,
    openai_schema_depth,openai_strict_violations,restore_open_maps)

LUNA='gpt-6-luna'
OPENAI='https://api.openai.com/v1/'
NEBIUS='https://api.tokenfactory.nebius.com/v1/'
PROMPT='Create a storage plinth in an estimated room'
SITE_MAP='$.scene_calls.items.anyOf[9].arguments.parameters'
PNG=ImageInput('room.png','image/png',b'\x89PNG\r\n\x1a\nfixture')


def config(base=OPENAI,model=LUNA):
    return ProviderConfig(base,'chat/completions',model,'UNUSED_SECURE_STORE',
        ProviderCapabilities(True,True,1,('image/png','image/jpeg')),timeout_s=300.,max_attempts=1)


class Captured(Exception):
    """Stops a real generation path right after its first dispatch."""


class Recorder:
    def __init__(self,*replies,halt=False):self.replies=list(replies);self.bodies=[];self.halt=halt
    async def complete(self,body,token,_config):
        self.bodies.append(deepcopy(body))
        if self.halt:raise Captured()
        value=self.replies.pop(0) if self.replies else {}
        return ChatCompletion(str(len(self.bodies)),body['model'],value if isinstance(value,str) else json.dumps(value),'stop',{})


class Scope:
    approved_render_review=True;approval_id='fixture-not-live';cache_identity='fixture'
    def bind(self,*_args):return None


def openai_transport(inner):
    return ConfiguredStageTransport({'observer':inner,'planner':inner},{'observer':config(),'planner':config()},
        {'observer':'openai','planner':'openai'},{'observer':'none','planner':'none'})


def pipeline(transport):
    return BudgetedPipeline(transport,policy=GenerationPolicy(),observer_model_id=LUNA,planner_model_id=LUNA,
        site_plan_version='2.2',stage_output_token_caps={'observer':4000,'planner':20000})


def configured_schema_names():
    return set(re.findall(r"'(twinpulse_[a-z0-9_]+)'",inspect.getsource(ConfiguredStageTransport.complete)))


def completion(value):
    return ChatCompletion('fixture',LUNA,value if isinstance(value,str) else json.dumps(value),'stop',{})


def rows(**values):
    return [dict(name=key,value=value) for key,value in values.items()]


def recipe_proposal(parameters):
    from test_model_recipe_planning import plinth_recipe
    recipe=plinth_recipe()
    call=dict(call_id='obj_plinth',tool='place_model_recipe',arguments=dict(id='plinth',kind='storage',
        model_id=recipe_model_id(recipe),recipe_sha256=recipe_digest(recipe),interpreter_version=recipe['interpreter_version'],
        recipe=recipe,parameters=parameters,center_m=[0,0],yaw_deg=0))
    return dict(plan_version='2.2',scene_id='plinth_room',summary='Estimated plinth room',image_observations='None',
        proposal_version=PROPOSAL_REVISION,coordinate_frame='local_xy',
        floor_call=dict(call_id='floor_1',tool='create_floor',arguments=dict(id='floor',center_m=[0,0],size_m=[6,6])),
        floor_evidence=dict(call_id='floor_1',observation_ids=[],basis='inferred',note='Estimated floor',user_quote=None),
        scene_calls=[call],call_evidence=[dict(call_id='obj_plinth',observation_ids=[],basis='user',
            note='Requested plinth',user_quote='storage plinth')])


class StrictRuleTests(unittest.TestCase):
    def test_each_rule_names_its_json_path_and_property_names_are_not_keywords(self):
        schema={'type':'object','additionalProperties':False,'required':['a','b','c','d','not'],'properties':{
            'a':{'type':'object','required':['x'],'properties':{'x':{'type':'number'}}},
            'b':{'type':'object','additionalProperties':False,'required':['x'],
                 'properties':{'x':{'type':'number'},'y':{'type':'string'}}},
            'c':{'type':'array','items':{'allOf':[{'type':'string'}]}},
            'd':{'type':'string','not':{'enum':['x']},'if':{'minLength':2},'then':{'maxLength':4}},
            'not':{'type':'string'}}}
        self.assertEqual(openai_strict_violations(schema),[('$.a','additional_properties_not_false'),
            ('$.b','required_not_all_properties'),('$.c.items','unsupported_allOf'),('$.d','unsupported_not'),
            ('$.d','unsupported_if'),('$.d','unsupported_then')])
        found=openai_strict_violations({'anyOf':[schema]})
        self.assertEqual(found[0],('$','root_not_object'))
        self.assertIn(('$.anyOf[0].a','additional_properties_not_false'),found)
        self.assertEqual(openai_strict_violations({'type':'object','additionalProperties':False,'required':[],'properties':{},
            '$defs':{'loose':{'type':'object','patternProperties':{'^x':{'type':'number'}},'dependentRequired':{}}}}),
            [('$.$defs.loose','unsupported_dependentRequired'),('$.$defs.loose','unsupported_patternProperties'),
             ('$.$defs.loose','additional_properties_not_false')])

    def test_depth_is_reported_but_never_blocks_a_request(self):
        node={'type':'number'}
        for _ in range(12):node={'type':'object','additionalProperties':False,'required':['n'],'properties':{'n':node}}
        self.assertEqual(openai_schema_depth(node),11)
        self.assertEqual(openai_schema_depth({'type':'object','additionalProperties':False,'required':['r'],
            'properties':{'r':{'$ref':'#/$defs/x'}},'$defs':{'x':deepcopy(node)}}),12)
        body={'model':LUNA,'max_tokens':100,'messages':[],'response_format':{'type':'json_schema',
            'json_schema':{'name':'deep','strict':True,'schema':node}}}
        self.assertEqual(openai_observer_body(body,reasoning_effort='none')['response_format']['json_schema']['schema'],node)

    def test_open_maps_become_bounded_rows_and_any_lossy_shape_fails_locally(self):
        number={'type':'number','minimum':0}
        schema={'type':'object','additionalProperties':False,'required':['p','q','r'],'properties':{
            'p':{'type':'object','additionalProperties':number},
            'q':{'type':'object','additionalProperties':{'type':'object','additionalProperties':{'type':'integer'}},
                 'maxProperties':4,'minProperties':1,'description':'Nested counts'},
            'r':{'type':'object','additionalProperties':{'type':'number'},'required':['w']}}}
        before=deepcopy(schema);wire=openai_map_rows(schema)
        self.assertEqual(schema,before)
        self.assertEqual(open_map_paths(schema),['$.p','$.q','$.q.additionalProperties'])
        self.assertEqual(wire['properties']['p'],{'type':'array','maxItems':32,'items':{'type':'object',
            'additionalProperties':False,'required':['name','value'],
            'properties':{'name':{'type':'string','maxLength':64},'value':number}}})
        nested=wire['properties']['q']
        self.assertEqual((nested['maxItems'],nested['minItems'],nested['description']),(4,1,'Nested counts'))
        self.assertEqual(nested['items']['properties']['value']['items']['properties']['value'],{'type':'integer'})
        # A required key cannot be spelled as rows without loss: it stays open and is rejected locally.
        self.assertEqual(wire['properties']['r'],schema['properties']['r'])
        body={'model':LUNA,'max_tokens':100,'messages':[],'response_format':{'type':'json_schema',
            'json_schema':{'name':'maps','strict':True,'schema':schema}}}
        with self.assertRaises(ProviderConfigurationError) as caught:openai_observer_body(body,reasoning_effort='none')
        self.assertEqual(caught.exception.code,'OPENAI_STRICT_SCHEMA_INVALID')
        self.assertIn('$.r additional_properties_not_false',str(caught.exception))
        del schema['properties']['r'];schema['required'].remove('r')
        self.assertEqual(openai_strict_violations(openai_observer_body(body|{'response_format':{'type':'json_schema',
            'json_schema':{'name':'maps','strict':True,'schema':schema}}})['response_format']['json_schema']['schema']),[])


class RestoreTests(unittest.TestCase):
    def schema(self):
        mapped={'type':'object','additionalProperties':{'type':'number'}}
        native={'type':'array','items':{'type':'object','additionalProperties':False,'required':['name','value'],
            'properties':{'name':{'type':'string'},'value':{'type':'number'}}}}
        branch=lambda kind,p:{'type':'object','additionalProperties':False,'required':['kind','p'],
            'properties':{'kind':{'const':kind},'p':p}}
        return normalize_json_schema({'type':'object','additionalProperties':False,'required':['calls','nested'],'properties':{
            'calls':{'type':'array','items':{'anyOf':[branch('map',mapped),branch('list',native)]}},
            'nested':{'type':'object','additionalProperties':{'type':'object','additionalProperties':{'type':'integer'}}}}})

    def test_rows_return_to_maps_only_in_the_discriminated_branch(self):
        value=dict(calls=[dict(kind='map',p=rows(w=1.5,d=2)),dict(kind='list',p=rows(w=3))],
            nested=[dict(name='a',value=rows(x=1)),dict(name='b',value=[])])
        restored=restore_open_maps(completion(value),self.schema())
        self.assertEqual(json.loads(restored.content),dict(calls=[dict(kind='map',p={'w':1.5,'d':2}),
            dict(kind='list',p=rows(w=3))],nested={'a':{'x':1},'b':{}}))
        self.assertEqual(restored.response_id,'fixture')

    def test_rewritten_text_keeps_every_value_and_stays_utf8(self):
        content='{"calls":[{"kind":"map","p":[{"name":"\\ud800","value":1e-07}]}],"nested":{"\\u00e9":{"x":-0}}}'
        restored=restore_open_maps(completion(content),self.schema())
        restored.content.encode('utf-8')
        self.assertIn('"é"',restored.content)
        self.assertEqual(json.loads(restored.content),dict(calls=[dict(kind='map',p={'\ud800':1e-07})],nested={'é':{'x':0}}))

    def test_ambiguous_malformed_and_non_row_content_is_left_for_host_validation(self):
        schema=self.schema()
        ambiguous=deepcopy(schema);ambiguous['properties']['calls']['items']['anyOf'][1]['properties']['kind']={'enum':['map'],'type':'string'}
        original=completion(dict(calls=[dict(kind='map',p=rows(w=1))],nested={}))
        self.assertIs(restore_open_maps(original,ambiguous),original)
        for content in ('{"calls":[],"nested":{"a":{"x":1}}}','{"calls":[],"nested":[{"name":"a"}]}',
                        '{"calls":[],"nested":[{"name":"a","value":[],"extra":1}]}','{"calls":[],"calls":[],"nested":[]}',
                        '{"calls":[', 'null'):
            original=completion(content)
            self.assertIs(restore_open_maps(original,schema),original)
        for result in (None,'routed'):self.assertIs(restore_open_maps(result,schema),result)
        plain=completion('{"a":[{"name":"x","value":1}]}')
        self.assertIs(restore_open_maps(plain,{'type':'object','additionalProperties':False,'required':['a'],'properties':{
            'a':{'type':'array','items':{'type':'object'}}}}),plain)

    def test_repeated_names_are_never_merged_and_fail_the_host_json_parser(self):
        repeated=[dict(name='w',value=1),dict(name='w',value=2)]
        # A nullable map is itself an anyOf: its repeated rows must stay one object, not [[name, value]] pairs.
        nullable={'type':'object','additionalProperties':False,'required':['p'],'properties':{
            'p':{'anyOf':[{'type':'null'},{'type':'object','additionalProperties':{'type':'number'}}]}}}
        for schema,value,text in ((self.schema(),dict(calls=[dict(kind='map',p=repeated)],nested=[]),
                                   '{"calls":[{"kind":"map","p":{"w":1,"w":2}}],"nested":{}}'),
                                  (nullable,dict(p=repeated),'{"p":{"w":1,"w":2}}')):
            with self.subTest(text=text):
                restored=restore_open_maps(completion(value),schema)
                self.assertEqual(restored.content,text)
                with self.assertRaises(InvalidProviderResponseError) as caught:_json_content(restored,'planner')
                self.assertEqual(caught.exception.code,'PROVIDER_JSON_DUPLICATE_KEY')


class SitePlanRoundTripTests(unittest.TestCase):
    def run_plan(self,*replies,transport=None):
        inner=Recorder(*replies)
        transport=transport(inner) if transport else openai_transport(inner)
        model=transport.planner_config.model_id if isinstance(transport,StageRoutingTransport) else LUNA
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=model,planner_model_id=model,
            site_plan_version='2.2',max_repairs=1)
        try:result=asyncio.run(provider.generate(GenerationRequest('round-trip',PROMPT),CancellationToken(),config(model=model)))
        except InvalidProviderResponseError as error:return inner,error
        return inner,result

    def parameters(self,result):
        return next(c for c in result.payload['calls'] if c['tool']=='place_model_recipe')['arguments']['parameters']

    def test_rows_come_back_as_the_map_and_pass_the_unchanged_host_executor(self):
        inner,result=self.run_plan(recipe_proposal(rows(width=1.2,depth=.6,height=.4)))
        self.assertEqual(self.parameters(result),{'width':1.2,'depth':.6,'height':.4})
        self.assertEqual(len(inner.bodies),1)
        wire=inner.bodies[0]['response_format']['json_schema']['schema']
        self.assertEqual(openai_strict_violations(wire),[])
        call=wire['properties']['scene_calls']['items']['anyOf'][9]
        self.assertEqual(call['properties']['tool']['enum'],['place_model_recipe'])
        self.assertEqual(call['properties']['arguments']['properties']['parameters']['type'],'array')

    def test_bad_values_are_still_rejected_by_host_validation(self):
        for parameters,code in ((rows(width=9.5,depth=.6,height=.4),'MODEL_RECIPE_INSTANCE_RANGE_INVALID'),
                                (rows(width=1.2,height=.4),'MODEL_RECIPE_INSTANCE_PARAMETERS_INVALID'),
                                (rows(width=1.2,depth=.6,height=.4,legs=4),'MODEL_RECIPE_INSTANCE_PARAMETERS_INVALID')):
            with self.subTest(code=code):
                inner,error=self.run_plan(recipe_proposal(parameters),recipe_proposal(parameters))
                self.assertIsInstance(error,InvalidProviderResponseError)
                self.assertIn(code,str(error))
                self.assertEqual(len(inner.bodies),2)
                self.assertIn('"parameters":{',inner.bodies[1]['messages'][-2]['content'])

    def test_repeated_names_fail_host_parsing_and_use_the_normal_single_repair(self):
        repeated=[dict(name='width',value=1.2),dict(name='width',value=1.),dict(name='height',value=.4)]
        inner,error=self.run_plan(recipe_proposal(repeated),recipe_proposal(rows(width=1.2,depth=.6,height=.4)))
        self.assertEqual(self.parameters(error),{'width':1.2,'depth':.6,'height':.4})
        self.assertIn('"width":1.2,"width":1.0',inner.bodies[1]['messages'][-2]['content'])
        self.assertIn('repeats JSON key',inner.bodies[1]['messages'][-1]['content'])

    def test_split_evaluation_openai_planner_restores_the_same_map(self):
        def split(inner):
            mini=config(model=OPENAI_MINI_SNAPSHOT)
            return StageRoutingTransport(inner,mini,inner,mini,reasoning_effort='low',openai_planner=True)
        inner,result=self.run_plan(recipe_proposal(rows(width=1.,depth=.6,height=.4)),transport=split)
        self.assertEqual(self.parameters(result),{'width':1.,'depth':.6,'height':.4})
        self.assertEqual(openai_strict_violations(inner.bodies[0]['response_format']['json_schema']['schema']),[])

    def test_nebius_wire_and_reply_are_unchanged(self):
        nano='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B';gemma='google/gemma-3-27b-it'
        reply=recipe_proposal(rows(width=1.2,depth=.6,height=.4))
        inner=Recorder(reply);configs={'observer':config(NEBIUS,gemma),'planner':config(NEBIUS,nano)}
        transport=ConfiguredStageTransport({'observer':inner,'planner':inner},configs,
            {'observer':'nebius','planner':'nebius'},{'observer':'low','planner':'low'})
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=gemma,planner_model_id=nano,
            site_plan_version='2.2',max_repairs=1)
        import test_budgeted_generation as fixtures
        body=provider.build_planner_body(GenerationRequest('nebius',PROMPT),fixtures.empty_observation())
        result=asyncio.run(transport.complete(body,CancellationToken(),configs['planner']))
        self.assertEqual(json.dumps(inner.bodies[0]),json.dumps(explicit_json_contract(body)))
        call=inner.bodies[0]['response_format']['json_schema']['schema']['properties']['scene_calls']['items']['anyOf'][9]
        self.assertEqual(call['properties']['arguments']['properties']['parameters'],
            {'type':'object','additionalProperties':{'type':'number'}})
        self.assertEqual(result.content,json.dumps(reply))


class EveryOpenAIStageSchemaTests(unittest.TestCase):
    """Actual builders through ConfiguredStageTransport to the OpenAI wire.

    Two host contracts are not expressible in OpenAI strict mode. They fail
    locally (no dispatch) until their owners change them; see KNOWN_LOCAL.
    """
    KNOWN_LOCAL={'twinpulse_model_recipe/no_children':[('$','root_not_object')],
        'twinpulse_semantic_patch':[('$.changes.bed.anyOf[1]','required_not_all_properties'),
                                    ('$.changes.cover.anyOf[1]','required_not_all_properties')]}

    def direct_bodies(self,planner):
        import test_budgeted_generation as fixtures
        import test_layout_experiment as layout_fixtures
        import test_render_review_loop as review_fixtures
        from test_model_recipe_planning import plinth_recipe
        from twinpulse_core.robot_task_plan import plan_schema
        from twinpulse_provider.generation_preview import room_seed_schema
        from twinpulse_provider.layout_experiment import response_schema
        from twinpulse_provider.model_capability_repair import capability_schema
        from twinpulse_provider.model_recipe_authoring import proportional_schema
        from twinpulse_provider.model_recipe_planning import definition_schema,selection_schema
        from twinpulse_provider.photo_layout import build_layout_body
        from twinpulse_provider.render_review import body as review_body
        from twinpulse_provider.repair_scope import delta_schema
        from twinpulse_provider.scene_edit_provider import feedback_proposal_json_schema
        from twinpulse_provider.semantic_scene import (batch_schema,checked_batch,checked_structure,compile_scene,
            revision,scene_draft,structure_schema)
        text=fixtures.text_request();photo=replace(text,images=(PNG,));empty=fixtures.empty_observation()
        request=GenerationRequest('recipe',PROMPT)
        draft=scene_draft(checked_structure(dict(summary='Room with plinth',room=dict(width_m=4,length_m=5,height_m=2.8),
            inventory=[dict(id='plinth',kind='storage',source=dict(basis='user',observation_ids=[],user_quote=PROMPT))]),
            request,empty))
        recipe=plinth_recipe();model=recipe_model_id(recipe)
        floor=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None)
        candidate=checked_batch({'plinth':dict(region='middle_centre',yaw_deg=0,model_id='common.storage',
            dimensions_m=[1.2,.8,.4],variant='standard',finish='natural',placement=floor)},draft,['plinth'])
        for identity,kind,model_id,size in (('cover','surface_covering','common.surface_covering',[1.,.6,.01]),
                                            ('prop','box','common.box',[.1,.1,.1])):
            candidate['inventory'].append(dict(id=identity,kind=kind,source=dict(basis='user',observation_ids=[],user_quote=PROMPT)))
            candidate['objects'][identity]=dict(region='middle_centre',yaw_deg=0,model_id=model_id,dimensions_m=size,
                variant='standard',finish='catalog_default',placement=dict(relation='surface',parent_id='plinth',
                    part='body',anchor='centre',elevation_m=None))
        support={'issues':[dict(code='PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE',target_ids=['cover'],
            actual=dict(reason='SURFACE_CAPACITY_EXCEEDED'),expected=dict(parent_id='plinth',part='body'))]}
        patch_draft,plan,diagnosis=layout_fixtures.sample()
        review_request,port,observation,_,_,review_draft=review_fixtures.case()
        review_plan,_=compile_scene(review_draft,observation,review_request)
        capture=asyncio.run(port.capture(review_plan,revision(review_draft),None,300));capture['plan']=review_plan
        body=planner.body
        return {
            'twinpulse_image_observation':planner.build_observer_body(photo),
            'twinpulse_render_review':review_body(review_request,review_draft,observation,capture,model=LUNA,cap=4000),
            'twinpulse_site_tool_plan_v2/text':planner.build_planner_body(text,empty),
            'twinpulse_site_tool_plan_v2/photo':planner.build_planner_body(photo,empty),
            'twinpulse_compact_photo_layout':build_layout_body(photo,empty,LUNA,None),
            'twinpulse_semantic_room':body('twinpulse_semantic_room',room_seed_schema(text),'Room',{}),
            'twinpulse_semantic_structure':body('twinpulse_semantic_structure',structure_schema(text,empty,bound=True),'S',{}),
            'twinpulse_model_resolution/selection':body('twinpulse_model_resolution',
                selection_schema(draft,{model:recipe},['plinth'],empty),'R',{}),
            'twinpulse_model_resolution/capability':body('twinpulse_model_resolution',
                capability_schema(candidate,support,{model:recipe},empty),'C',{}),
            'twinpulse_model_recipe/no_children':body('twinpulse_model_recipe',definition_schema('storage',[]),'D',{}),
            'twinpulse_model_recipe/children':body('twinpulse_model_recipe',definition_schema('storage',['box']),'D',{}),
            'twinpulse_semantic_batch/builtin':body('twinpulse_semantic_batch',batch_schema(fixtures.draft()['inventory'],['bed']),'B',{}),
            'twinpulse_semantic_batch/recipe':body('twinpulse_semantic_batch',batch_schema(draft['inventory'],['plinth'],
                recipes={model:recipe},selections={'plinth':model}),'B',{}),
            'twinpulse_semantic_patch':body('twinpulse_semantic_patch',response_schema(delta_schema(patch_draft,diagnosis),None),'P',{}),
            # Product feedback is Nebius-only (generate_feedback); the transport itself can still route it.
            'twinpulse_scene_feedback':body('twinpulse_scene_feedback',feedback_proposal_json_schema(),'F',{}),
            'twinpulse_library_recipe':body('twinpulse_library_recipe',proportional_schema(),'L',{}),
            'twinpulse_robot_task':body('twinpulse_robot_task',plan_schema(),'T',{}),
        }

    def first_dispatches(self,planner):
        from twinpulse_core.environment_photo import VERSION as PHOTO_VERSION
        from twinpulse_core.robot_task_plan import CAPABILITIES,VERSION as TASK_VERSION
        from twinpulse_provider.environment_move import VERSION as MOVE_VERSION,generate_environment_move
        from twinpulse_provider.environment_photo import generate_environment_photo
        from twinpulse_provider.library_recipe import generate_recipe
        from twinpulse_provider.robot_task_planner import generate_robot_task
        import test_budgeted_generation as fixtures
        class Preview:supports_incremental_preview=True
        token=CancellationToken
        return {
            'twinpulse_room_observation':lambda:planner.generate(replace(fixtures.text_request(),images=(PNG,),
                inference_scope=Scope(),render_review_port=Preview()),token(),config()),
            'twinpulse_asset_observation':lambda:generate_recipe(planner,GenerationRequest('asset','A small shelf',
                images=(PNG,),inference_scope=Scope()),token(),config()),
            'twinpulse_environment_photo':lambda:generate_environment_photo(planner,GenerationRequest('photo',json.dumps(dict(
                existing_props=[],scanned_objects=[dict(category='table',label='Table')])),images=(PNG,),
                schema_version=PHOTO_VERSION,inference_scope=Scope()),token(),config()),
            'twinpulse_environment_move':lambda:generate_environment_move(planner,GenerationRequest('move',json.dumps(dict(
                object_id='Env_1',text='Move it left 10 cm')),schema_version=MOVE_VERSION,inference_scope=Scope()),token(),config()),
            'twinpulse_robot_task/generated':lambda:generate_robot_task(planner,GenerationRequest('task',json.dumps(dict(
                text='Explore the room and come back',robot_kind='sim',capabilities=list(CAPABILITIES))),
                schema_version=TASK_VERSION,inference_scope=Scope()),token(),config()),
            'twinpulse_library_recipe/generated':lambda:generate_recipe(planner,GenerationRequest('library','A small shelf',
                inference_scope=Scope()),token(),config()),
        }

    def test_every_configured_openai_schema_is_strict_or_fails_locally(self):
        wires={}
        inner=Recorder();planner=pipeline(openai_transport(inner))
        for label,body in self.direct_bodies(planner).items():
            inner.bodies.clear()
            stage=config()
            with self.subTest(label=label):
                raw=explicit_json_contract(body)['response_format']['json_schema']['schema']
                if label in self.KNOWN_LOCAL:
                    with self.assertRaises(ProviderConfigurationError) as caught:
                        asyncio.run(planner._transport.complete(body,CancellationToken(),stage))
                    self.assertEqual(caught.exception.code,'OPENAI_STRICT_SCHEMA_INVALID')
                    self.assertEqual(openai_strict_violations(openai_map_rows(raw)),self.KNOWN_LOCAL[label])
                    self.assertEqual(inner.bodies,[])
                    wires[label]=None
                    continue
                asyncio.run(planner._transport.complete(body,CancellationToken(),stage))
                wires[label]=inner.bodies[0]
        halting=Recorder(halt=True);planner=pipeline(openai_transport(halting))
        for label,start in self.first_dispatches(planner).items():
            halting.bodies.clear()
            with self.subTest(label=label):
                with self.assertRaises(Captured):asyncio.run(start())
                wires[label]=halting.bodies[0]
        for label,wire in wires.items():
            if wire is None:continue
            with self.subTest(label=label):
                envelope=wire['response_format']['json_schema']
                self.assertEqual(envelope['name'],label.split('/')[0])
                self.assertIs(envelope['strict'],True)
                self.assertNotIn('max_tokens',wire)
                self.assertEqual(openai_strict_violations(envelope['schema']),[])
        self.assertEqual({label.split('/')[0] for label in wires},configured_schema_names())
        # The same counts as the launch audit; OpenAI's own depth rule stays unverified.
        depth={label:openai_schema_depth(wire['response_format']['json_schema']['schema'])
               for label,wire in wires.items() if wire is not None}
        self.assertEqual((depth['twinpulse_site_tool_plan_v2/text'],depth['twinpulse_scene_feedback']),(9,11))

    def test_capability_rows_choose_the_recipe_branch_and_pass_checked_capability(self):
        from test_recipe_authoring import table
        from twinpulse_provider.model_capability_repair import capability_schema,checked_capability
        from twinpulse_provider.semantic_scene import revision
        bodies=self.direct_bodies(pipeline(openai_transport(Recorder())))
        schema=explicit_json_contract(bodies['twinpulse_model_resolution/capability'])['response_format']['json_schema']['schema']
        self.assertEqual(open_map_paths(schema),['$.replacements.plinth.anyOf[1].recipe_parameters'])
        candidate=self.capability_candidate()
        value=dict(base_revision=revision(candidate),replacements={'plinth':dict(model={'recipe':table()},
            dimensions_m=[1.2,.8,1.4],variant='standard',finish='recipe_materials',recipe_parameters=rows(width=1.2,depth=.8,height=1.4),
            support_bindings=dict(cover='lower',prop=dict(parent_id='cover',part='top',anchor='centre')))})
        inner=Recorder(value);transport=openai_transport(inner)
        diagnosis={'issues':[dict(code='PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE',target_ids=['cover'],
            actual=dict(reason='SURFACE_CAPACITY_EXCEEDED'),expected=dict(parent_id='plinth',part='body'))]}
        body=pipeline(transport).body('twinpulse_model_resolution',capability_schema(candidate,diagnosis,{},None),'C',{})
        restored=json.loads(asyncio.run(transport.complete(body,CancellationToken(),config())).content)
        self.assertEqual(restored['replacements']['plinth']['recipe_parameters'],{'width':1.2,'depth':.8,'height':1.4})
        result,_=checked_capability(restored,candidate,diagnosis,{})
        self.assertEqual(result['objects']['prop']['placement']['parent_id'],'cover')

    def capability_candidate(self):
        from twinpulse_provider.semantic_scene import checked_batch,checked_structure,scene_draft
        import test_budgeted_generation as fixtures
        request=GenerationRequest('recipe',PROMPT)
        draft=scene_draft(checked_structure(dict(summary='Room with plinth',room=dict(width_m=4,length_m=5,height_m=2.8),
            inventory=[dict(id='plinth',kind='storage',source=dict(basis='user',observation_ids=[],user_quote=PROMPT))]),
            request,fixtures.empty_observation()))
        floor=dict(relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None)
        candidate=checked_batch({'plinth':dict(region='middle_centre',yaw_deg=0,model_id='common.storage',
            dimensions_m=[1.2,.8,.4],variant='standard',finish='natural',placement=floor)},draft,['plinth'])
        for identity,kind,model_id,size in (('cover','surface_covering','common.surface_covering',[1.,.6,.01]),
                                            ('prop','box','common.box',[.1,.1,.1])):
            candidate['inventory'].append(dict(id=identity,kind=kind,source=dict(basis='user',observation_ids=[],user_quote=PROMPT)))
            candidate['objects'][identity]=dict(region='middle_centre',yaw_deg=0,model_id=model_id,dimensions_m=size,
                variant='standard',finish='catalog_default',placement=dict(relation='surface',parent_id='plinth',
                    part='body',anchor='centre',elevation_m=None))
        return candidate


class ResponsesPathFindingTests(unittest.TestCase):
    """Report only: the Responses API path and listed raw schemas are not routed or rewritten here."""
    def test_responses_path_schemas_have_no_strict_findings(self):
        from twinpulse_provider.schema import scene_tool_plan_json_schema
        from twinpulse_provider.scene_edit_provider import scene_edit_proposal_json_schema
        for schema in (scene_tool_plan_json_schema(),scene_edit_proposal_json_schema(),
                       scene_tool_plan_json_schema(required_call_slots=True)):
            self.assertEqual(openai_strict_violations(schema),[])

    def test_raw_host_schemas_keep_their_known_findings(self):
        from twinpulse_core.robot_task_plan import plan_schema
        from twinpulse_provider.photo_layout import layout_schema
        from twinpulse_provider.schema import site_proposal_json_schema
        self.assertEqual(openai_strict_violations(site_proposal_json_schema(photo=False)),
            [(SITE_MAP,'additional_properties_not_false')])
        self.assertEqual(openai_strict_violations(plan_schema()),[])
        self.assertEqual(openai_strict_violations(layout_schema(PROMPT)),[])


if __name__=='__main__':unittest.main()
