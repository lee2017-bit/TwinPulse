# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure financial/schedule guards. No inference, processes or actual approval."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import unittest
from scripts.benchmark_campaign import (initialize,validate,admission,reserve_next,settle,
    exposure,child_command,eligibility,eligibility_matrix)


class BenchmarkCampaignTests(unittest.TestCase):
    def test_ordinary_minimum_blocks_before_launch_or_reservation_and_text_skips_observer(self):
        from twinpulse_app.generation_approval import full_context_reserve,minimum_initial_reserve
        prepared=deepcopy(self.prepared)
        observer='deepseek-ai/DeepSeek-V4.1-Flash';planner='nvidia/nemotron-3-super-120b-a12b'
        prepared['model_catalog']=dict(schema_version='stage-model-catalog-1.0',verified_at=self.now.isoformat(),
            valid_until=(self.now+timedelta(hours=4)).isoformat(),source_sha256='b'*64,models=[
                dict(model_id=observer,visible=True,modalities=['text','image'],context_tokens=1048000,
                    input_per_million='0.3',output_per_million='1.2'),
                dict(model_id=planner,visible=True,modalities=['text'],context_tokens=262144,
                    input_per_million='0.3',output_per_million='0.9')])
        for config in prepared['configs']:
            roles={s:dict(provider='nebius',model=observer if s in ('observer','critic') else planner)
                for s in ('observer','planner','repair','critic')}
            config.update(roles=roles,stage_output_token_caps=dict(observer=40000,planner=40000))
        prepared['packets']['text']['photo']={'path':'TEST_ONLY_NOT_READ'}
        grant=deepcopy(self.grant);grant['providers'].pop('openai');grant['trial_usd']='0.30'
        state=initialize(prepared,grant);before=deepcopy(state)
        gate=admission(state,self.now)
        expected=minimum_initial_reserve([full_context_reserve(row,40000)
            for row in prepared['model_catalog']['models']])
        self.assertEqual(str(expected),'0.5916864')
        self.assertEqual(gate['code'],'INITIAL_RESERVATION_EXCEEDS_TRIAL_CAP')
        self.assertEqual(gate['minimum_initial_reserve_usd'],str(expected))
        self.assertEqual(state,before);self.assertEqual(state['runs'],[])
        with self.assertRaisesRegex(ValueError,'INITIAL_RESERVATION'):reserve_next(state,self.now)
        affordable=deepcopy(grant);affordable['trial_usd']='0.60'
        self.assertTrue(admission(initialize(prepared,affordable),self.now)['allowed'])
        prepared['packets']['text']['photo']=None
        self.assertEqual(str(minimum_initial_reserve([full_context_reserve(
            prepared['model_catalog']['models'][1],40000)])),'0.2292864')
        self.assertTrue(admission(initialize(prepared,grant),self.now)['allowed'])

    def setUp(self):
        self.now=datetime(2026,10,10,tzinfo=timezone.utc)
        roles=dict(observer=dict(provider='openai',model='gpt-6-luna'),
            planner=dict(provider='nebius',model='nvidia/Nemotron-3_5-Lightning'))
        roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
        self.prepared=dict(manifest_sha256='a'*64,configs=[dict(config_id=c,roles=deepcopy(roles)) for c in ('a','b')],
            packets={'text':dict(goal=dict(expected='arrival'),external_transmission_allowed=True)},
            jobs=[dict(job_id=str(i),config_id=c,case_id='text',block=0) for i,c in enumerate(('a','b'))])
        self.grant=dict(schema_version='benchmark-authorization-1.0',authorization_id='test-only-not-paid',
            manifest_sha256='a'*64,approved_at=self.now.isoformat(),expires_at=(self.now+timedelta(hours=4)).isoformat(),
            human_approval='TEST FIXTURE NOT AUTHORIZATION',request_cap=24,trial_usd='1.00',admission_reserve_s=1800,
            providers={p:dict(limit_usd='5',existing_exposure_usd='.1',original_input=True,derived_render=True)
                for p in ('nebius','openai')})
        self.state=initialize(self.prepared,self.grant)

    def summary(self):
        return dict(status='FAIL',audit_status='PASS',unknown_requests=0,pending_locks=0,
            cost_by_provider=dict(nebius='.02',openai='.03'),held_by_provider=dict(nebius='0',openai='0'),rows=[])

    def test_reservation_resume_preserves_failed_trial_and_no_repeat(self):
        state=reserve_next(self.state,self.now);before=deepcopy(state)
        self.assertEqual(str(exposure(state)['openai']),'1.10')
        self.assertEqual(admission(state,self.now)['code'],'UNSETTLED_PRIOR_RUN_RESERVATION_HELD')
        state=settle(state,'0',self.summary());validate(state,self.prepared,self.grant)
        self.assertEqual(state['runs'][0]['status'],'FAIL');self.assertEqual(before['runs'][0]['status'],'RESERVED')
        next_state=reserve_next(state,self.now);self.assertEqual(next_state['runs'][-1]['job_id'],'1')
        self.assertEqual(len(next_state['runs']),2)
        with self.assertRaisesRegex(ValueError,'ALREADY_SETTLED'):settle(state,'0',self.summary())

    def test_unknown_and_billing_hold_not_refunded(self):
        state=reserve_next(self.state,self.now);bad=self.summary();bad['unknown_requests']=1
        with self.assertRaisesRegex(ValueError,'RESERVATION_HELD'):settle(state,'0',bad)
        summary=self.summary();summary['held_by_provider']['openai']='.4'
        summary['rows']=[dict(provider='openai',http_status=402)]
        state=settle(state,'0',summary)
        self.assertEqual(str(exposure(state)['openai']),'0.53')
        self.assertEqual(admission(state,self.now)['code'],'PROVIDER_PAYMENT_REQUIRED_STOP')

    def test_whole_paired_block_needs_full_budget_not_reduced_policy(self):
        self.grant['providers']['openai']['limit_usd']='2'
        state=initialize(self.prepared,self.grant)
        self.assertEqual(admission(state,self.now)['code'],'PAIRED_BLOCK_BUDGET_INSUFFICIENT')
        self.assertEqual(state['runs'],[])

    def test_expiry_future_scope_cohort_and_tamper(self):
        self.assertEqual(admission(self.state,self.now-timedelta(seconds=1))['code'],'APPROVAL_NOT_YET_VALID')
        self.assertIn('EXPIRED',admission(self.state,self.now+timedelta(hours=4))['code'])
        grant=deepcopy(self.grant);grant['human_approval']='changed'
        with self.assertRaisesRegex(ValueError,'COHORT_OR_APPROVAL'):validate(self.state,self.prepared,grant)
        grant=deepcopy(self.grant);grant['providers']['openai']['derived_render']=False
        with self.assertRaisesRegex(ValueError,'SCOPE_OR_EXPOSURE'):initialize(self.prepared,grant)
        state=reserve_next(self.state,self.now);state['runs'][0]['reserved_usd']['openai']='0'
        with self.assertRaisesRegex(ValueError,'RESERVATION_CHANGED'):validate(state,self.prepared,self.grant)

    def test_five_distinct_models_not_five_pairs_and_output_limit(self):
        probe=dict(role='planner',provider='nebius',model_id='same',actual_dispatched=True,status='FAIL',root_code='ROOT')
        self.state['failure_probes']=[deepcopy(probe) for _ in range(5)]
        self.assertTrue(admission(self.state,self.now)['allowed'])
        for i,row in enumerate(self.state['failure_probes']):row['model_id']=str(i)
        self.assertEqual(admission(self.state,self.now)['code'],'FIVE_DISTINCT_MODELS_SAME_ROOT_STOP')
        state=settle(reserve_next(initialize(self.prepared,self.grant),self.now),'0',self.summary())
        state['runs'][0]['summary']['rows']=[dict(finish_reason='length')]
        self.assertEqual(admission(state,self.now)['code'],'OUTPUT_LIMIT_STOP')

    def test_text_child_command_has_no_photo_annotations_or_model_answer(self):
        from pathlib import Path
        command=child_command(self.state,self.prepared['jobs'][0],Path('output'),Path('manifest.json'))
        self.assertIn('--benchmark-manifest',command);self.assertIn('--approval-text',command)
        self.assertNotIn('--photo',command);self.assertNotIn('annotations',' '.join(command))
        self.prepared['packets']['text']['goal']['expected']='rejection'
        self.assertEqual(eligibility(self.prepared),[])

    def test_typed_output_truncation_stops_when_rejected_row_loses_finish_reason(self):
        summary=self.summary()
        summary.update(failure_code='PROVIDER_OUTPUT_TRUNCATED',rows=[
            dict(provider='openai',status='rejected',finish_reason=None,
                 usage=dict(completion_tokens=20000),stage='twinpulse_render_review')])
        state=settle(reserve_next(self.state,self.now),'0',summary)
        original=deepcopy(state)
        self.assertEqual(admission(state,self.now)['code'],'OUTPUT_LIMIT_STOP')
        with self.assertRaisesRegex(ValueError,'OUTPUT_LIMIT_STOP'):reserve_next(state,self.now)
        self.assertEqual(state,original)
        self.assertEqual(str(exposure(state)['openai']),'0.13')

    def test_normal_completion_at_token_count_is_not_inferred_truncation(self):
        summary=self.summary()
        summary.update(failure_code='REPAIR_STALLED',rows=[
            dict(provider='openai',status='received',finish_reason='stop',
                 usage=dict(completion_tokens=20000))])
        state=settle(reserve_next(self.state,self.now),'0',summary)
        self.assertTrue(admission(state,self.now)['allowed'])

    def test_ineligible_model_and_negative_tasks_visible_without_dispatch_or_quality_failure(self):
        prepared=deepcopy(self.prepared)
        prepared['configs'][1]['roles']['planner']['model']='unsupported-text-model'
        matrix=eligibility_matrix(prepared)
        self.assertEqual(matrix[0]['status'],'REVIEWED_ADAPTER_SUPPORTED')
        self.assertEqual(matrix[1]['status'],'INELIGIBLE')
        self.assertIn('MODEL_NOT_ELIGIBLE_IN_REVIEWED_ACTUAL_ADAPTER',matrix[1]['reasons'])
        prepared['packets']['text']['goal']['expected']='clarification'
        self.assertEqual(eligibility_matrix(prepared)[0]['status'],'REVIEWED_ADAPTER_SUPPORTED')
        self.assertEqual(eligibility_matrix(prepared)[1]['status'],'INELIGIBLE')
        self.assertEqual(self.state['runs'],[])

    def test_catalog_models_supported_but_embedding_wrong_role_or_expired_not_dispatched(self):
        catalog=dict(schema_version='stage-model-catalog-1.0',verified_at='2026-10-10T00:00:00+00:00',
            valid_until='2026-10-16T00:00:00+00:00',source_sha256='b'*64,models=[
                dict(model_id='new/model',visible=True,modalities=['text'],context_tokens=32000,
                     input_per_million='0.1',output_per_million='0.2')])
        prepared=deepcopy(self.prepared);prepared['model_catalog']=catalog
        for config in prepared['configs']:
            config['roles']['planner']['model']='new/model';config['roles']['repair']=deepcopy(config['roles']['planner'])
        self.assertEqual(eligibility(prepared),[])
        state=initialize(prepared,self.grant)
        self.assertTrue(admission(state,self.now)['allowed'])
        prepared['model_catalog']['models'][0]['modalities']=[]
        self.assertTrue(eligibility(prepared));self.assertEqual(state['runs'],[])
        state['prepared']['model_catalog']['valid_until']='2026-10-10T00:00:01+00:00'
        self.assertEqual(admission(state,self.now+timedelta(seconds=2))['code'],'MODEL_CATALOG_EXPIRED_OR_INVALID')

    def test_pass_or_unattributed_failure_breaks_role_streak_and_binding_is_checked(self):
        summary=self.summary();identity=self.prepared['configs'][0]['roles']['planner']
        summary['rows']=[dict(stage='twinpulse_semantic_structure',provider=identity['provider'],model_id=identity['model'])]
        summary['failure_probe']=dict(role='planner',provider=identity['provider'],model_id=identity['model'],
            status='FAIL',actual_dispatched=True,root_code='ROOT')
        state=settle(reserve_next(self.state,self.now),'0',summary)
        summary=deepcopy(summary);summary['status']='PASS';summary.pop('failure_probe')
        state=settle(reserve_next(state,self.now),'1',summary);validate(state,self.prepared,self.grant)
        planner=[p for p in state['failure_probes'] if p['role']=='planner']
        self.assertEqual([p['status'] for p in planner],['FAIL','PASS'])
        bad=deepcopy(state);bad['runs'][0]['summary']['failure_probe']['model_id']='another'
        with self.assertRaisesRegex(ValueError,'ROLE_BINDING'):validate(bad,self.prepared,self.grant)

    def test_budget_uses_runner_two_decimal_contract_not_delayed_preflight_failure(self):
        self.grant['trial_usd']='.5'
        with self.assertRaisesRegex(ValueError,'TRIAL_BUDGET_INVALID'):initialize(self.prepared,self.grant)

    def test_explicit_p2_twelve_call_grant_preserves_scope_and_old_twenty_four(self):
        from pathlib import Path
        grant=deepcopy(self.grant);grant['request_cap']=12
        state=initialize(self.prepared,grant)
        command=child_command(state,self.prepared['jobs'][0],Path('output'),Path('manifest.json'))
        self.assertEqual(command[command.index('--request-cap')+1],'12')
        self.assertEqual(state['authorization']['providers'],self.grant['providers'])
        self.assertEqual(self.state['authorization']['request_cap'],24)
        with self.assertRaisesRegex(ValueError,'COHORT_OR_APPROVAL'):
            validate(self.state,self.prepared,grant)
        for bad in (True,11,13,25):
            grant['request_cap']=bad
            with self.assertRaisesRegex(ValueError,'RESOURCE_POLICY'):initialize(self.prepared,grant)


if __name__=='__main__':unittest.main()
