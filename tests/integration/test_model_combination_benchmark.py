# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline budget/report guards. No inference, keys, UI or engine."""
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.run_model_combination_benchmark import exposure,public_summary,wilson,percentile,repeated_failure_stop,blocked_providers,simulation_failure_codes,ready_storage_bound


class BenchmarkTests(unittest.TestCase):
    def test_shared_output_gate_accepts_typed_failure_without_raw_finish_reason(self):
        from scripts.benchmark_campaign import output_limit_reached
        self.assertTrue(output_limit_reached(dict(failure_code='PROVIDER_OUTPUT_TRUNCATED',
            rows=[dict(status='rejected',finish_reason=None)])))
        self.assertTrue(output_limit_reached(dict(rows=[dict(finish_reason='length')])))
        self.assertFalse(output_limit_reached(dict(failure_code='REPAIR_STALLED',
            rows=[dict(finish_reason='stop',usage=dict(completion_tokens=20000))])))
        self.assertFalse(output_limit_reached({}))

    def test_text_storage_binding_does_not_invent_source_photo_review(self):
        checkpoint=dict(plan_sha256='current',render_history=[])
        draft=dict(plan_sha256='current')
        self.assertTrue(ready_storage_bound(checkpoint,draft,photo=False))
        self.assertFalse(ready_storage_bound(checkpoint,draft,photo=True))
        self.assertFalse(ready_storage_bound(checkpoint,dict(plan_sha256='old'),photo=False))
        self.assertFalse(ready_storage_bound(checkpoint,{},photo=False))
        checkpoint['render_history']=[dict(status='uncertain')]
        self.assertTrue(ready_storage_bound(checkpoint,draft,photo=True))
    def test_unknown_and_unfinished_keep_full_provider_reservation(self):
        case={'limits_usd':{'nebius':'5','openai':'1'},'runs':[
            {'reserved_usd':{'nebius':'1','openai':'1'}},
            {'audit_status':'PASS','reserved_usd':{'nebius':'1'},'cost_by_provider':{'nebius':'.01','openai':'0'}}]}
        self.assertEqual(str(exposure(case)['nebius']),'1.01')
        self.assertEqual(str(exposure(case)['openai']),'1')
        case['runs'].append({'reserved_usd':{'nebius':'0','openai':'.01'}})
        with self.assertRaisesRegex(ValueError,'CAMPAIGN_BUDGET_EXCEEDED'):exposure(case)

    def test_recorded_http_rejection_does_not_refund_unverified_billing(self):
        case={'limits_usd':{'nebius':'5','openai':'1'},'runs':[
            {'audit_status':'PASS','reserved_usd':{'openai':'1'},
             'cost_by_provider':{'openai':'.01'},'held_by_provider':{'openai':'.115'}}]}
        self.assertEqual(str(exposure(case)['openai']),'0.125')

    def test_public_metrics_keep_failures_versions_and_small_sample_uncertainty(self):
        def run(status,version):
            return dict(audit_status='PASS',status=status,inference_source_sha256=version,
                generation_ready=status=='PASS',actual_sim_full=status=='PASS',repair_requests=1,
                actual_requests=1,render_reviews=1,final_render_status='uncertain',failure_code='REPAIR_STALLED' if status=='FAIL' else None,
                cost_by_provider={'nebius':'.01','openai':'0'},rows=[dict(model_id='m',elapsed_s=2,finish_reason='stop')],
                secret='never export',room_position=[1,2,3],raw='private')
        case=dict(status='RUNNING',runs=[run('PASS','v1'),run('FAIL','v1'),run('PASS','v2')])
        result=public_summary(case)
        self.assertEqual(len(result['cohorts']),2)
        self.assertEqual(result['cohorts'][0]['samples'],2)
        self.assertEqual(result['cohorts'][0]['full_journey_success_rate'],.5)
        self.assertGreater(wilson(2,2)[1]-wilson(2,2)[0],.6)
        self.assertNotIn('never export',str(result));self.assertNotIn('room_position',str(result))
        self.assertNotIn('private',str(result['trials']))
        self.assertEqual(len(result['trials']),3)
        self.assertFalse(result['independent_generalization_test'])

    def test_roles_are_not_merged_and_quantiles_are_explicit(self):
        def run(observer,planner):
            return dict(audit_status='PASS',status='FAIL',inference_source_sha256='v',
                observer_model=observer,planner_model=planner,generation_ready=False,actual_sim_full=False,
                repair_requests=0,actual_requests=1,render_reviews=0,final_render_status='NOT_REACHED',
                failure_code='REPAIR_STALLED',cost_by_provider={'nebius':'.01','openai':'0'},
                rows=[dict(model_id=observer,elapsed_s=2,finish_reason='stop')])
        result=public_summary(dict(status='RUNNING',runs=[run('a','b'),run('b','a')]))
        self.assertEqual(len(result['cohorts']),2)
        self.assertEqual(percentile([1,2,3,4],.95),3.85)
        self.assertIsNone(percentile([],.95))

    def test_five_distinct_same_failure_stops_but_success_resets_streak(self):
        runs=[dict(audit_status='PASS',status='FAIL',observer_model='o'+str(i),planner_model='p',
                   root_failure_codes=['PACKING'],failure_code='REPAIR_STALLED') for i in range(5)]
        self.assertTrue(repeated_failure_stop(dict(runs=runs)))
        runs[2]['status']='PASS'
        self.assertFalse(repeated_failure_stop(dict(runs=runs)))

    def test_public_markdown_never_exports_private_trial_data(self):
        from scripts.export_combination_benchmark import render
        case=dict(status='RUNNING',limits_usd={'nebius':'5','openai':'1'},runs=[],
                  source_image='PRIVATE_IMAGE',coordinates=[123,456],api_key='PRIVATE_SECRET')
        markdown,metrics=render(case)
        self.assertNotIn('PRIVATE_',markdown)
        self.assertNotIn('123',markdown)
        self.assertFalse(metrics['source_images_included'])
        self.assertFalse(metrics['physical_robot_pass'])

    def test_payment_rejection_blocks_only_that_provider_without_retry(self):
        case={'runs':[{'rows':[{'provider':'nebius','http_status':402},
                              {'provider':'openai','http_status':200}]}]}
        self.assertEqual(blocked_providers(case),{'nebius'})
        self.assertFalse(blocked_providers(case)&{'openai'})

    def test_terminal_sim_code_is_not_a_harness_timeout_or_private_message(self):
        browser={'conversation':{'messages':[
            {'role':'assistant','status':'failed','content':'SIM_TARGET_NO_REACHABLE_APPROACH (simulation_goal_rejected). PRIVATE_ROOM'}]}}
        self.assertEqual(simulation_failure_codes(browser),['SIM_TARGET_NO_REACHABLE_APPROACH'])
        browser['conversation']['messages'][0]['status']='completed'
        self.assertEqual(simulation_failure_codes(browser),[])
        browser['conversation']['messages'][0]['status']='failed'
        browser['conversation']['messages'].append({'role':'assistant','status':'failed','content':'Other later failure'})
        self.assertEqual(simulation_failure_codes(browser),[])

    def test_deferred_trials_are_public_but_not_failed_model_denominator(self):
        case={'status':'PARTIAL_PROVIDER_BLOCKED','runs':[],
              'deferred_cases':[{'id':'a-2','status':'NOT_RUN','reason':'NEBIUS_HTTP_402','secret':'PRIVATE'}]}
        metrics=public_summary(case)
        self.assertEqual(metrics['cohorts'],[])
        self.assertEqual(metrics['deferred_cases'],[{'id':'a-2','status':'NOT_RUN','reason':'NEBIUS_HTTP_402'}])
        self.assertNotIn('PRIVATE',str(metrics))

    def test_invalid_cpu_snapshot_is_disclosed_not_used_as_wall_timing(self):
        metrics=public_summary({'status':'PARTIAL_PROVIDER_BLOCKED','runs':[
            {'actual_requests':0,'cpu_profile_top_self':[{'self_s':1,'cumulative_s':.2}]}]})
        self.assertEqual(metrics['cpu_profile_anomalous_trials'],1)
        self.assertEqual(metrics['trials'],[])


if __name__=='__main__':unittest.main()
