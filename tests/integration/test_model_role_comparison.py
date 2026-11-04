# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import unittest
from copy import deepcopy
from scripts.compare_model_roles_live import FailureStreak, plan_cases, wire_for, failure_fingerprint


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
        import json
        from pathlib import Path
        from scripts.compare_model_roles_live import ChatCompletion, host_reply
        from twinpulse_provider.model_recipe_planning import checked_definition, definition_schema
        saved=Path(__file__).resolve().parents[2]/'packages/twinpulse_provider/tests/fixtures/repair_stall_2026-10-26/draft.json'
        recipe=json.loads(saved.read_text(encoding='utf-8'))['model_recipes']['local.830361779608ac8f83396984']
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


if __name__=='__main__':unittest.main()
