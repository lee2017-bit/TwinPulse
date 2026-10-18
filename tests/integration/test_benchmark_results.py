# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic accounting/statistic examples, never actual benchmark results."""
from copy import deepcopy
import unittest
from scripts.benchmark_results import STAGES,account,paired_interval,same_root_model_streak,compare_paired


class BenchmarkResultTests(unittest.TestCase):
    def test_audited_diagnostic_acceptance_has_its_own_denominator_never_full_pass(self):
        self.prepared['jobs'][0]['split']='diagnostic'
        self.prepared['packets']={'case0':{'goal':{'expected':'clarification'}}}
        row=self.row(0);row['stages']['semantic_goal_arrival']='NOT_EVALUATED';row['stages']['stop']='NOT_EVALUATED'
        row['diagnostic_verdict']={'status':'PASS','expected_outcome':'clarification','code':'SIM_TARGET_CLARIFICATION',
            'evidence_sha256':'a'*64,'semantic_goal_arrival':False,'physical_authority':False}
        result=account(self.prepared,[row]);group=next(g for g in result['groups'] if g['split']=='diagnostic')
        self.assertEqual(group['qualified_full_pass'],0);self.assertEqual(group['qualified_diagnostic_pass'],1)
        self.assertEqual(group['diagnostic_rate_over_actual_started'],1);self.assertIsNone(group['completion_rate_over_actual_started'])
        self.assertEqual(group['diagnostic_acceptance'],'EVALUATED')
        row['audit_status']='FAIL'
        group=next(g for g in account(self.prepared,[row])['groups'] if g['split']=='diagnostic')
        self.assertEqual(group['qualified_diagnostic_pass'],0)

    def setUp(self):
        self.prepared=dict(manifest_sha256='a'*64,configs=[dict(config_id='first')],
            jobs=[dict(job_id=str(i),case_id='case'+str(i),room_group='room'+str(i),
                config_id='first',repeat=1,modality='photo',split='holdout') for i in range(4)])

    def row(self,identity,**changes):
        return dict(job_id=str(identity),manifest_sha256='a'*64,started=True,evidence_mode='actual_fresh',
            audit_status='PASS',stages={stage:'PASS' for stage in STAGES},
            estimated_usd={'nebius':'0.10','openai':'0.01'},held_usd={'nebius':'0'},**changes)

    def test_audit_failure_unknown_quality_and_not_run_do_not_disappear(self):
        rows=[self.row(0),self.row(1),self.row(2)]
        rows[1]['audit_status']='FAIL';rows[2]['stages']['independent_quality']='NOT_EVALUATED'
        result=account(self.prepared,rows);group=result['groups'][0]
        self.assertEqual(len(result['outcomes']),4)
        self.assertEqual(group['planned'],4);self.assertEqual(group['actual_fresh_started'],3)
        self.assertEqual(group['audit_failed'],1);self.assertEqual(group['not_run'],1)
        self.assertEqual(group['quality_not_evaluated'],1);self.assertEqual(group['qualified_full_pass'],1)
        self.assertEqual(group['estimated_usd']['nebius'],'0.30')
        self.assertEqual(group['estimated_cost_per_qualified_success'],'0.33')

    def test_replay_and_fixture_are_not_actual_full_success(self):
        rows=[self.row(0),self.row(1)];rows[0]['evidence_mode']='fixture';rows[1]['evidence_mode']='saved_replay'
        group=account(self.prepared,rows)['groups'][0]
        self.assertEqual(group['qualified_full_pass'],0)
        self.assertIsNone(group['completion_rate_over_actual_started'])
        self.assertEqual(group['non_actual'],2)
        self.assertEqual(group['stages']['current_render']['pass'],0)

    def test_duplicate_cohort_and_fake_not_run_stage_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):account(self.prepared,[self.row(0),self.row(0)])
        row=self.row(0);row['manifest_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'COHORT_CHANGED'):account(self.prepared,[row])
        row=self.row(0);row['started']=False
        with self.assertRaisesRegex(ValueError,'NOT_RUN_CANNOT_PASS'):account(self.prepared,[row])

    def test_missing_cost_does_not_become_zero_or_cost_winner(self):
        row=self.row(0);row['estimated_usd']=None
        group=account(self.prepared,[row])['groups'][0]
        self.assertFalse(group['cost_complete']);self.assertIsNone(group['estimated_cost_per_qualified_success'])
        row['estimated_usd']={'nebius':'NaN'}
        with self.assertRaisesRegex(ValueError,'COST_INVALID'):account(self.prepared,[row])

    def test_held_unknown_billing_cannot_be_a_cost_winner(self):
        row=self.row(0);row['held_usd']={'nebius':'0.50'}
        group=account(self.prepared,[row])['groups'][0]
        self.assertFalse(group['cost_complete']);self.assertIsNone(group['estimated_cost_per_qualified_success'])
        self.assertEqual(group['held_usd']['nebius'],'0.50')

    def test_identical_repeated_success_is_not_zero_uncertainty(self):
        result=paired_interval([0.,0.])
        self.assertEqual(result['method'],'BOUNDED_HOEFFDING')
        self.assertLess(result['interval'][0],0);self.assertGreater(result['interval'][1],0)
        result=paired_interval([1.]*30)
        self.assertLess(result['interval'][0],1)

    def test_cluster_interval_is_seed_reproducible(self):
        values=[-1.,0.,1.,.5,-.5]*3
        self.assertEqual(paired_interval(values,seed=4,resamples=1000),paired_interval(values,seed=4,resamples=1000))

    def test_paired_comparison_uses_rooms_not_repetitions_as_independent_samples(self):
        prepared=deepcopy(self.prepared);prepared['configs'].append(dict(config_id='second'))
        for i,job in enumerate(prepared['jobs']):
            job['room_group']='room'+str(i//2);job['case_id']='case'+str(i//2);job['repeat']=i%2+1
        originals=deepcopy(prepared['jobs'])
        prepared['jobs'] += [{**job,'job_id':job['job_id']+'b','config_id':'second'} for job in originals]
        records=[self.row(i) for i in range(4)]
        records += [{**self.row(i),'job_id':str(i)+'b'} for i in range(4)]
        result=compare_paired(account(prepared,records),'first','second','photo')
        self.assertEqual(result['independent_rooms'],2);self.assertEqual(result['paired_trials'],4)
        self.assertLess(result['interval'][0],0);self.assertGreater(result['interval'][1],0)
        records[0]['stages']['independent_quality']='NOT_EVALUATED'
        result=compare_paired(account(prepared,records),'first','second','photo')
        self.assertEqual(result['status'],'INCONCLUSIVE')

    def test_five_pairs_of_same_model_do_not_count_as_five_models(self):
        rows=[dict(role='planner',provider='nebius',model_id='same',status='FAIL',
            root_code='PACKING',actual_dispatched=True) for _ in range(5)]
        self.assertFalse(same_root_model_streak(rows,'planner')['stop'])
        for i,row in enumerate(rows):row['model_id']='model'+str(i)
        self.assertTrue(same_root_model_streak(rows,'planner')['stop'])
        rows[2]['status']='PASS';self.assertFalse(same_root_model_streak(rows,'planner')['stop'])
        self.assertFalse(same_root_model_streak(rows,'observer')['stop'])

    def test_negative_cases_never_become_full_arrival_pass_and_keep_separate_denominator(self):
        prepared=deepcopy(self.prepared)
        prepared['packets']={j['case_id']:dict(goal=dict(expected='arrival')) for j in prepared['jobs']}
        prepared['jobs'][1]['split']='diagnostic';prepared['packets']['case1']['goal']['expected']='rejection'
        prepared['jobs'][2]['split']='diagnostic';prepared['packets']['case2']['goal']['expected']='clarification'
        rows=[self.row(i) for i in range(3)]
        result=account(prepared,rows)
        positive=next(g for g in result['groups'] if g['expected_outcome']=='arrival')
        self.assertEqual(positive['planned'],2);self.assertEqual(positive['qualified_full_pass'],1)
        for group in (g for g in result['groups'] if g['expected_outcome']!='arrival'):
            self.assertEqual(group['planned'],1);self.assertEqual(group['qualified_full_pass'],0)
            self.assertFalse(group['primary_completion_population'])
            self.assertIsNone(group['completion_rate_over_actual_started'])
            self.assertEqual(group['stages']['semantic_goal_arrival']['pass'],0)
            self.assertEqual(group['diagnostic_acceptance'],'NOT_EVALUATED')
        self.assertEqual(sum(o['qualified_full_pass'] for o in result['outcomes']),1)
        self.assertEqual(rows[1]['stages']['semantic_goal_arrival'],'PASS')  # Source retained, not re-labelled.

    def test_negative_task_cannot_leak_to_primary_split_or_paired_completion_statistics(self):
        prepared=deepcopy(self.prepared);prepared['packets']={'case0':dict(goal=dict(expected='rejection'))}
        with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_SPLIT'):account(prepared,[])
        prepared['jobs'][0]['split']='diagnostic'
        result=account(prepared,[])
        self.assertEqual(compare_paired(result,'first','second','photo',split='diagnostic')['reason'],
                         'DIAGNOSTIC_OUTCOME_NOT_ARRIVAL_COMPARISON')


if __name__=='__main__':unittest.main()
