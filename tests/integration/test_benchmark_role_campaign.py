# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline matrix/scope invariants, not actual model or Isaac success."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.benchmark_role_campaign import public_cases,planned,remaining,aggregate
from scripts.compare_model_roles_live import wire_for

class PublicRoleCampaignTests(unittest.TestCase):
    def models(self):
        return [dict(model_id='gpt-6-luna',provider='openai',use_cases=['text','image']),
                dict(model_id='vision',provider='nebius',use_cases=['text','image']),
                dict(model_id='text',provider='nebius',use_cases=['text'])]

    def test_two_repetitions_each_input_and_role_no_embedding(self):
        cases=[dict(case_id='room-'+str(i)) for i in range(3)]
        jobs=planned(self.models(),cases)
        self.assertEqual(len(jobs),30)
        self.assertEqual(jobs,planned(self.models(),cases))
        self.assertEqual(len({j['job_id'] for j in jobs}),len(jobs))
        for case in cases:
            for model in self.models():
                for role in ('observer','planner'):
                    selected=[j for j in jobs if j['case_id']==case['case_id'] and j['model_id']==model['model_id'] and j['role']==role]
                    self.assertEqual({j['repeat'] for j in selected},{1,2} if role=='planner' or 'image' in model['use_cases'] else set())

    def test_declared_luna_seed_first_not_quality_selected(self):
        jobs=planned(self.models(),[dict(case_id='one')])
        first=next(j for j in jobs if j['role']=='observer' and j['repeat']==1)
        self.assertEqual(first['model_id'],'gpt-6-luna')
        self.assertTrue(all(j['role']=='observer' for j in jobs[:4]))

    def test_old_exposure_not_refunded_or_cap_reset(self):
        self.assertEqual(Decimal(remaining('1.36741503')),Decimal('3.63258497'))
        for value in ('5','6','NaN','-1'):
            with self.assertRaises(ValueError):remaining(value)

    def test_source_permission_and_duplicate_room_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'public.jpg').write_bytes(b'local fixture not sent')
            spec=dict(schema_version='pilot-dataset-spec-1.0',cases=[dict(case_id='photo',room_group='one',photo='public.jpg',prompt='fixture',
                source=dict(external_transmission_allowed=True,public_release_allowed=True,license='CC BY-SA fixture'))])
            rows=public_cases(spec,root/'spec.json');self.assertEqual(len(rows),1)
            spec['cases'][0]['source']['public_release_allowed']=False
            with self.assertRaisesRegex(ValueError,'PERMISSION'):public_cases(spec,root/'spec.json')
            spec['cases'][0]['source']['public_release_allowed']=True
            spec['cases'].append(deepcopy(spec['cases'][0]))
            with self.assertRaisesRegex(ValueError,'INDEPENDENT_INPUT'):public_cases(spec,root/'spec.json')

    def test_current_adapter_does_not_force_nano_flag_on_unrelated_model(self):
        body=dict(model='another/model',max_tokens=40000,messages=[dict(role='system',content='Return JSON.'),dict(role='user',content='fixture')],
                  response_format={'type':'json_schema','json_schema':dict(name='fixture',strict=True,
                      schema=dict(type='object',properties={},required=[],additionalProperties=False))})
        self.assertNotIn('chat_template_kwargs',wire_for(body,'nebius',current_adapter=True))
        body['model']='nvidia/Nemotron-3_5-Lightning'
        self.assertEqual(wire_for(body,'nebius',current_adapter=True)['chat_template_kwargs'],dict(enable_thinking=False))

    def test_summary_keeps_failure_and_never_turns_missing_into_pass(self):
        jobs=planned(self.models(),[dict(case_id='one')])
        result=dict(job_id=jobs[0]['job_id'],status='FAIL',actual_calls=1,room_group='one',failure_code='OUTPUT_LIMIT',
                    attempts=[dict(elapsed_s=2)],estimated_or_reserved_usd='.1')
        table=aggregate(jobs,[result],self.models())
        self.assertEqual(sum(r['pass_count'] for r in table),0)
        self.assertEqual(sum(r['fail_count'] for r in table),1)
        self.assertEqual(sum(r['not_run'] for r in table),len(jobs)-1)

if __name__=='__main__':unittest.main()
