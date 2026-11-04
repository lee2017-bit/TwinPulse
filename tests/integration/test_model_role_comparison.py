# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from copy import deepcopy
from scripts.compare_model_roles_live import FailureStreak, plan_cases, wire_for, failure_fingerprint


def saved_recipe():
    """The saved 2026-10-26 factory's local bollard recipe: it has no children, so its schema root is an anyOf."""
    saved=Path(__file__).resolve().parents[2]/'packages/twinpulse_provider/tests/fixtures/repair_stall_2026-10-26/draft.json'
    return json.loads(saved.read_text(encoding='utf-8'))['model_recipes']['local.830361779608ac8f83396984']


class RoleComparisonTests(unittest.TestCase):
    def row(self, model, status='FAIL', code='BAD_FORMAT'):
        return dict(model_id=model,status=status,failure_code=code,http_status=400)

    def test_five_distinct_models_not_five_retries(self):
        streak=FailureStreak()
        for _ in range(7):self.assertFalse(streak.observe(self.row('one')))
        for name in ('two','three','four'):self.assertFalse(streak.observe(self.row(name)))
        self.assertTrue(streak.observe(self.row('five')))

    def test_success_or_different_root_resets(self):
        streak=FailureStreak()
        for name in ('a','b','c','d'):self.assertFalse(streak.observe(self.row(name)))
        self.assertFalse(streak.observe(self.row('e','PASS')))
        self.assertFalse(streak.observe(self.row('f')))
        self.assertFalse(streak.observe(self.row('g',code='GEOMETRY')))
        self.assertEqual(streak.models,['g'])

    def test_host_preflight_failure_does_not_count_as_model_failure(self):
        streak=FailureStreak()
        for name in ('a','b','c','d','e','f'):
            row=self.row(name);row['actual_calls']=0
            self.assertFalse(streak.observe(row))
        self.assertEqual(streak.models,[])

    def test_every_model_can_construct_before_dispatch(self):
        from scripts.compare_model_roles_live import BudgetedPipeline, GenerationPolicy
        for name in ('gpt-6-luna','nvidia/Nemotron-3_5-Lightning','nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
                     'nvidia/Nemotron-3-Ultra-550b-a55b','MiniMaxAI/MiniMax-M3','Qwen/Qwen3.8-27B'):
            BudgetedPipeline(None,policy=GenerationPolicy(),observer_model_id='shared-observation',
                planner_model_id=name,site_plan_version='2.2',planner_template_no_thinking=False,
                stage_output_token_caps={'observer':20000,'planner':20000})

    def test_typed_issue_not_aggregate_failure(self):
        one=self.row('a');two=self.row('b')
        one['contract_report']={'issues':[{'code':'MISSING_ITEM'}]}
        two['contract_report']={'issues':[{'code':'OUT_OF_BOUNDS'}]}
        self.assertNotEqual(failure_fingerprint(one),failure_fingerprint(two))

    def test_two_trials_and_modality_filter(self):
        models=[dict(provider='nebius',model_id='vision',visible=True,use_cases=['text','image']),
                dict(provider='nebius',model_id='text',visible=True,use_cases=['text']),
                dict(provider='nebius',model_id='embedding',visible=True,use_cases=['retrieval'])]
        cases=plan_cases(dict(models=models,openai_luna_visible=True))
        self.assertEqual(len(cases),10)
        self.assertFalse(any(m['model_id']=='embedding' for r,m,n in cases))
        self.assertFalse(any(m['model_id']=='text' and r=='observer' for r,m,n in cases))
        self.assertEqual(sum(m['model_id']=='gpt-6-luna' for r,m,n in cases),4)

    def test_wire_keeps_contract_only_official_compatibility(self):
        body=dict(model='gpt-6-luna',max_tokens=20000,temperature=0,
            chat_template_kwargs={'enable_thinking':False},
            messages=[dict(role='system',content='Return JSON.'),dict(role='user',content='same source')],
            response_format={'type':'json_schema','json_schema':{'name':'role','strict':True,
                'schema':{'type':'object','properties':{'v':{'const':'yes'}},'required':['v'],'additionalProperties':False}}})
        before=deepcopy(body)
        wire=wire_for(body,'openai')
        self.assertEqual(body,before)
        self.assertEqual(wire['max_completion_tokens'],20000)
        self.assertEqual(wire['reasoning_effort'],'none')
        self.assertNotIn('chat_template_kwargs',wire)
        self.assertEqual(wire['messages'][-1],body['messages'][-1])
        self.assertEqual(wire['response_format']['json_schema']['schema']['properties']['v'],{'enum':['yes'],'type':'string'})

    def test_openai_reply_gets_the_host_shape_back_before_host_validation(self):
        from scripts.compare_model_roles_live import ChatCompletion, host_reply
        from twinpulse_provider.model_recipe_planning import checked_definition, definition_schema
        recipe=saved_recipe()
        body=dict(model='gpt-6-luna',max_tokens=20000,temperature=0,
            messages=[dict(role='system',content='Return JSON.'),dict(role='user',content='same source')],
            response_format={'type':'json_schema','json_schema':{'name':'twinpulse_model_recipe','strict':True,
                'schema':definition_schema(recipe['kind'],[])}})
        # A recipe without children has an anyOf root, which OpenAI receives as {"value": root}.
        self.assertEqual(wire_for(body,'openai')['response_format']['json_schema']['schema']['required'],['value'])
        reply=ChatCompletion('fixture','gpt-6-luna',json.dumps({'value':recipe}),'stop',{})
        restored=host_reply(reply,body,'openai')
        self.assertEqual(json.loads(restored.content),recipe)
        checked_definition(json.loads(restored.content),recipe['kind'],'bollard_1',[])
        self.assertIs(host_reply(reply,body,'nebius'),reply)  # a Nebius reply already has the host spelling


class Transport:
    """Stands in for AuditedChatTransport offline: keeps each wire body and answers with fixed JSON."""
    def __init__(self, reply):
        self.reply, self.bodies, self.calls, self.record_validation = reply, [], [], Mock()

    async def complete(self, body, token, config):
        from scripts.compare_model_roles_live import ChatCompletion
        self.bodies.append(deepcopy(body))
        return ChatCompletion('offline', body['model'], json.dumps(self.reply), 'stop', {})


class RunCaseHostShapeTests(unittest.IsolatedAsyncioTestCase):
    """run_case with the OpenAI role model, offline: each reply gets its host shape back and the host schema judges it."""

    async def run_role(self, role, reply, service=None):
        from scripts.compare_model_roles_live import LUNA, run_case
        transport=Transport(reply)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);photo=root/'fixture.jpg';photo.write_bytes(b'offline fixture, never sent')
            ledger=SimpleNamespace(state=dict(requests=[]),lock_path=root/'absent.lock')
            services=patch('scripts.compare_model_roles_live.GenerationService',service) if service else nullcontext()
            with patch('scripts.compare_model_roles_live.AuditedChatTransport',return_value=transport),services:
                row=await run_case(root/'out',role,LUNA,1,dict(openai=SimpleNamespace(load=lambda:'unused-offline')),
                    ledger,None,dict(photo_sha256='fixture',observation_sha256='fixture'),photo=photo,prompt='fixture')
        return row,transport

    async def test_observer_reply_is_judged_by_the_host_schema(self):
        from twinpulse_provider.observation_alignment import unknown_alignment
        def observation(category):
            return dict(schema_version='1.5',summary='Offline fixture',entities=[dict(id='seen_bed',kind='static_obstacle',
                description='bed',confidence=.9,role='object',category=category,region='unknown',spatial_confidence=.9,
                instance_count=1,footprint_alignment=unknown_alignment())],relations=[],dimensions=[],ambiguities=['Unmeasured'])
        row,transport=await self.run_role('observer',observation('bed'))
        self.assertEqual((row['status'],row['categories']),('PASS',['bed']))
        self.assertEqual(transport.bodies[0]['reasoning_effort'],'none')  # the OpenAI wire was sent
        # The wire shares repeated enums by $ref; the host schema still lists every category.
        row,_=await self.run_role('observer',observation('not_a_category'))
        self.assertEqual((row['status'],row['error']),('FAIL','OBSERVER_SCHEMA_INVALID'))
        self.assertEqual(row['contract_report']['issues'],
            [dict(code='SEMANTIC_VARIANT_INVALID',path='$.entities[0]',severity='error')])

    async def test_planner_reuse_hands_the_pipeline_host_shaped_replies(self):
        from twinpulse_provider import CancellationToken
        from twinpulse_provider.model_recipe_planning import checked_definition, definition_schema
        from twinpulse_provider.nebius_pipeline import _json_content
        recipe=saved_recipe();received=[]
        class OneDefinition:
            """Stands in for GenerationService: one real recipe request through run_case's planner transport."""
            def __init__(self, pipeline, config, **_):
                self.pipeline, self.config = pipeline, config
            async def generate(self, request):
                body=self.pipeline.body('twinpulse_model_recipe',definition_schema(recipe['kind'],[]),'Define it.',{})
                value=_json_content(await self.pipeline._transport.complete(body,CancellationToken(),self.config),'planner')
                received.append(value)
                checked_definition(value,recipe['kind'],'bollard_1',[])
                return SimpleNamespace(plan=SimpleNamespace(to_dict=dict,calls=[]),provider_provenance={})
        row,transport=await self.run_role('planner',{'value':recipe},OneDefinition)
        # OpenAI received the {"value": root} spelling and answered in it; the pipeline got the recipe itself.
        self.assertEqual(transport.bodies[0]['response_format']['json_schema']['schema']['required'],['value'])
        self.assertEqual(received,[recipe])
        self.assertEqual(row['status'],'PASS')


if __name__=='__main__':unittest.main()
