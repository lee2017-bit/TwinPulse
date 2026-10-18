# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline normalized-evidence counterexamples; not actual benchmark results."""
from copy import deepcopy
import json
import unittest
from scripts.collect_comparative_benchmark import stages_from_evidence,public_report,markdown
from scripts.benchmark_results import account


class ComparativeCollectorTests(unittest.TestCase):
    def setUp(self):
        self.summary=dict(rows=[dict(status='received',finish_reason='stop')],generation_completed=True,generation_ready=True)
        draft=dict(revision='scene',plan_sha256='plan',input_revision='input')
        self.result=dict(browser=dict(workflow=dict(site_draft=draft),frames=[dict(applied_revision='scene')],
            semantic_arrival=dict(runtime_state='completed',telemetry_available=True,applied_revision='scene',distance_to_goal_m=.03),
            stop=dict(runtime_state='paused',telemetry_available=True,applied_revision='scene',position_m=[0,0,0]),
            reload_evidence=dict(status='PASS',plan_sha256='plan',input_revision='input',builds_before=1,builds_after=1,
                runs_before=3,runs_after=3,restored_run_authorization=False,runtime_state='paused')),
            render_review_closed_backend_reopen=dict(status='PASS',plan_sha256='plan',source_unchanged=True,automatic_dispatch=False))

    def test_quality_unscored_even_if_ordinary_journey_passed(self):
        stages=stages_from_evidence(self.summary,self.result,'NOT_EVALUATED')
        self.assertEqual(stages['semantic_goal_arrival'],'PASS');self.assertEqual(stages['reload'],'PASS')
        self.assertEqual(stages['independent_quality'],'NOT_EVALUATED')
        self.result['browser']['semantic_arrival']['distance_to_goal_m']=.1
        self.assertEqual(stages_from_evidence(self.summary,self.result,'PASS')['semantic_goal_arrival'],'FAIL')

    def test_stale_render_preview_arrival_reload_and_reopen_not_current_pass(self):
        self.result['browser']['frames'][0]['applied_revision']='old'
        self.result['browser'].pop('semantic_arrival')
        self.result['browser']['arrival']=dict(runtime_state='completed',distance_to_goal_m=0)
        self.result['browser']['reload_evidence']['runs_after']=4
        self.result['render_review_closed_backend_reopen']['plan_sha256']='another'
        stages=stages_from_evidence(self.summary,self.result,'PASS')
        self.assertEqual(stages['current_render'],'NOT_REACHED')
        self.assertEqual(stages['semantic_goal_arrival'],'FAIL');self.assertEqual(stages['reload'],'NOT_REACHED')
        self.assertEqual(stages['reopen'],'NOT_REACHED')

    def test_unknown_length_payment_and_missing_stages_do_not_disappear(self):
        self.summary['rows'][0].update(status='rejected',finish_reason='length')
        stages=stages_from_evidence(self.summary,self.result,'NOT_EVALUATED')
        self.assertEqual(stages['provider_response'],'FAIL')
        self.summary.update(generation_completed=False,generation_ready=False)
        self.result['browser']={}
        stages=stages_from_evidence(self.summary,self.result,'NOT_EVALUATED')
        self.assertEqual(stages['generation'],'FAIL');self.assertEqual(stages['stop'],'NOT_REACHED')

    def test_public_export_whitelist_planned_denominator_and_split_separation(self):
        prepared=dict(manifest_sha256='a'*64,configs=[dict(config_id='a',roles={},settings_sha256='b'*64)],
            jobs=[dict(job_id='1',config_id='a',modality='photo',split='development',case_id='private-one',room_group='same',repeat=1),
                  dict(job_id='2',config_id='a',modality='photo',split='holdout',case_id='private-two',room_group='different',repeat=1)])
        collected=dict(accounting=account(prepared,[]),private_details=[dict(job_id='1',quality=None,
            secret='PRIVATE_RAW_MARKER',position=[12,34],photo_path='PRIVATE_PHOTO')],exposure_usd=dict(nebius='0',openai='0'))
        report=public_report(collected,prepared);encoded=json.dumps(report)+markdown(report)
        for value in ('PRIVATE_RAW_MARKER','PRIVATE_PHOTO','private-one','private-two','position'):
            self.assertNotIn(value,encoded)
        self.assertEqual(len(report['groups']),2);self.assertEqual(len(report['trials']),2)
        self.assertTrue(all(g['qualified_full_pass']==0 and g['not_run']==1 for g in report['groups']))
        self.assertFalse(report['physical_robot_pass']);self.assertEqual(report['rankings'],'NOT_COMPUTED')

    def test_negative_public_trial_does_not_claim_arrival_or_mutate_private_evidence(self):
        roles=dict(observer=dict(provider='openai',model='gpt-6-luna'),
                   planner=dict(provider='nebius',model='nvidia/Nemotron-3_5-Lightning'))
        roles.update(critic=deepcopy(roles['observer']),repair=deepcopy(roles['planner']))
        prepared=dict(manifest_sha256='a'*64,configs=[dict(config_id='a',roles=roles,settings_sha256='b'*64)],
            packets={'private-case':dict(goal=dict(expected='rejection'),external_transmission_allowed=True)},
            jobs=[dict(job_id='1',config_id='a',modality='text',split='diagnostic',case_id='private-case',
                       room_group='private-room',repeat=1)])
        from scripts.benchmark_results import STAGES
        record=dict(job_id='1',manifest_sha256='a'*64,started=True,evidence_mode='actual_fresh',audit_status='PASS',
                    stages={s:'PASS' for s in STAGES},estimated_usd=dict(nebius='.1',openai='.1'),held_usd={})
        accounting=account(prepared,[record]);original=deepcopy(accounting)
        report=public_report(dict(accounting=accounting,private_details=[],exposure_usd={}),prepared)
        self.assertEqual(accounting,original)
        self.assertEqual(report['trials'][0]['expected_outcome'],'rejection')
        self.assertEqual(report['trials'][0]['stages']['semantic_goal_arrival'],'NOT_EVALUATED')
        self.assertFalse(report['trials'][0]['qualified_full_pass'])
        self.assertEqual(report['execution_eligibility'][0]['status'],'REVIEWED_ADAPTER_SUPPORTED')
        self.assertFalse(report['trials'][0]['qualified_diagnostic_pass'])  # no proof, no diagnostic PASS
        self.assertEqual(report['account_model_availability'],'NOT_CHECKED_NO_NETWORK')
        self.assertNotIn('private-case',json.dumps(report))
        self.assertEqual(record['stages']['semantic_goal_arrival'],'PASS')

    def test_verified_diagnostic_never_promotes_idle_to_moving_stop_or_full_pass(self):
        from scripts.benchmark_diagnostic import validate_diagnostic
        from tests.integration.test_benchmark_diagnostic import proof
        packet,receipt=proof()
        self.summary['diagnostic_goal_acceptance']=validate_diagnostic(packet,receipt)
        self.result['browser']['reload_evidence']['runtime_state']='completed'
        stages=stages_from_evidence(self.summary,self.result,'NOT_EVALUATED')
        self.assertEqual(stages['semantic_goal_arrival'],'NOT_EVALUATED')
        self.assertEqual(stages['stop'],'NOT_EVALUATED')
        self.assertEqual(stages['reload'],'PASS')
        self.result['browser']['reload_evidence']['runs_after']=4
        self.assertEqual(stages_from_evidence(self.summary,self.result,'NOT_EVALUATED')['reload'],'NOT_REACHED')


if __name__=='__main__':unittest.main()
