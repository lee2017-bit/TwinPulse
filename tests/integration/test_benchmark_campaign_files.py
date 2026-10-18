# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""File-level controller/collector fixtures. No actual calls or runtime PASS."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import tests.integration.test_benchmark_protocol as protocol_data
from scripts.benchmark_protocol import prepare,effective_settings_sha,checked_manifest
from scripts.benchmark_campaign import initialize,manifest_main,reserve_next,write_atomic,validate
from scripts.collect_comparative_benchmark import collector,public_report,audit_frozen_settings
import scripts.collect_comparative_benchmark as collect_cli
from twinpulse_provider.generation_policy import GenerationPolicy
from dataclasses import replace


class BenchmarkCampaignFilesTests(unittest.TestCase):
    def setUp(self):
        data=protocol_data.BenchmarkProtocolTests();data.setUp();self.addCleanup(data.doCleanups)
        self.root=data.root;self.value=deepcopy(data.value)
        roles=dict(observer=dict(provider='openai',model='gpt-6-luna'),
                   planner=dict(provider='nebius',model='nvidia/Nemotron-3_5-Lightning'))
        roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
        policy=replace(GenerationPolicy(),max_requests=24,external_final_review=True,initial_timeout_s=420,final_timeout_s=180)
        self.route=dict(observer=dict(key_id='NOT_A_KEY',model_id=roles['observer']['model'],max_output_tokens=20000),
            planner=dict(key_id='NOT_A_KEY',model_id=roles['planner']['model'],max_output_tokens=20000,thinking_mode='disabled'),
            generation_policy=policy.to_dict())
        self.value['configs']=[dict(config_id='reviewed',roles=roles,settings_sha256=effective_settings_sha(self.route,roles))]
        for case in self.value['cases']:case['source']['external_transmission_allowed']=True
        self.manifest=self.root/'manifest.json';self.save(self.manifest,self.value)
        self.prepared=prepare(self.manifest);self.now=datetime.now(timezone.utc)
        self.grant=dict(schema_version='benchmark-authorization-1.0',authorization_id='offline-not-approval',
            manifest_sha256=self.prepared['manifest_sha256'],approved_at=self.now.isoformat(),
            expires_at=(self.now+timedelta(hours=4)).isoformat(),human_approval='SYNTHETIC FILE TEST ONLY',
            providers={p:dict(limit_usd='20',existing_exposure_usd='0',original_input=True,derived_render=True)
                for p in ('nebius','openai')},request_cap=24,trial_usd='1.00',admission_reserve_s=1800)
        self.authorization=self.root/'approval-fixture.json';self.save(self.authorization,self.grant)
        self.directory=self.root/'campaign';self.directory.mkdir()

    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8')

    def summary(self):
        return dict(status='FAIL',audit_status='PASS',unknown_requests=0,pending_locks=0,
            cost_by_provider=dict(nebius='.02',openai='0'),held_by_provider=dict(nebius='0',openai='0'),
            rows=[],generation_completed=False,generation_ready=False,actual_requests=0,
            failure_origin='harness_or_engine',root_failure_codes=[],model_http_wall_s=0)

    def args(self,**changed):
        value=dict(manifest=self.manifest,authorization=self.authorization,directory=self.directory,
                   initialize=False,reconcile=False,run_next=False)
        return SimpleNamespace(**{**value,**changed})

    def test_initialize_report_and_reconcile_never_dispatch_or_reset_consumption(self):
        with patch('scripts.benchmark_campaign.subprocess.run',side_effect=AssertionError('NO_CHILD')),redirect_stdout(StringIO()):
            manifest_main(self.args(initialize=True));manifest_main(self.args())
            with self.assertRaises(FileExistsError):manifest_main(self.args(initialize=True))
            state=reserve_next(initialize(self.prepared,self.grant),self.now)
            write_atomic(self.directory/'manifest-campaign.json',state)
            original=self.summary()
            with patch('scripts.run_model_combination_benchmark.summarize_run',return_value=original) as audit:
                manifest_main(self.args(reconcile=True));manifest_main(self.args(reconcile=True))
                audit.assert_called_once()
        current=json.loads((self.directory/'manifest-campaign.json').read_text())
        validate(current,self.prepared,self.grant)
        self.assertTrue(current['runs'][0]['settled']);self.assertEqual(current['runs'][0]['status'],'FAIL')
        self.assertEqual(len(current['runs']),1);self.assertFalse((self.directory/'manifest-dispatch-lock.json').exists())

    def test_unknown_reconcile_and_existing_lock_never_erase_reservations(self):
        state=reserve_next(initialize(self.prepared,self.grant),self.now)
        path=self.directory/'manifest-campaign.json';write_atomic(path,state,create=True);before=path.read_bytes()
        with patch('scripts.run_model_combination_benchmark.summarize_run',side_effect=ValueError('UNKNOWN')):
            with self.assertRaisesRegex(ValueError,'UNKNOWN'):manifest_main(self.args(reconcile=True))
        self.assertEqual(path.read_bytes(),before)
        lock=self.directory/'manifest-dispatch-lock.json';lock.write_text('foreign owner')
        with self.assertRaises(FileExistsError):manifest_main(self.args(reconcile=True))
        self.assertEqual(lock.read_text(),'foreign owner');self.assertEqual(path.read_bytes(),before)

    def test_collector_file_path_keeps_fail_not_run_and_missing_evidence_cost(self):
        state=reserve_next(initialize(self.prepared,self.grant),self.now);job=self.prepared['jobs'][0]
        target=self.directory/job['job_id'];packet=self.prepared['packets'][job['case_id']]
        receipt=dict(benchmark_manifest_sha256=self.prepared['manifest_sha256'],case_id=job['case_id'],
            config_id=job['config_id'],settings_sha256=self.prepared['configs'][0]['settings_sha256'],
            generation_only=False,route=self.route,cost_limit_usd='1.00',benchmark_expires_at=self.grant['expires_at'])
        self.save(target/'approval.json',receipt);self.save(target/'benchmark-case.json',packet)
        self.save(target/'reviewed-settings/provider_stage_routing.json',dict(schema_version='1.0',route=self.route))
        self.save(target/'run-1/result.json',dict(ordinary_live_audit=True,inference_source_unchanged=True,
            browser=dict(photo_inference='LIVE' if packet['modality']=='photo' else 'NOT_APPLICABLE',robot_connections=0)))
        self.save(target/'run-1/runtime/active_project.json',dict(site_draft=None))
        manifest=checked_manifest(self.value,self.root)
        with patch('scripts.run_model_combination_benchmark.summarize_run',return_value=self.summary()):
            report=collector(self.prepared,state,self.directory,manifest)
        self.assertEqual(report['private_details'][0]['status'],'FAIL')
        self.assertTrue(all(g['qualified_full_pass']==0 for g in report['accounting']['groups']))
        self.assertEqual(sum(g['not_run'] for g in report['accounting']['groups']),len(self.prepared['jobs'])-1)
        self.assertFalse(public_report(report,self.prepared)['physical_robot_pass'])
        tampered=deepcopy(state);tampered['runs'][0].update(settled=True,summary=self.summary())
        tampered['runs'][0]['summary']['cost_by_provider']['nebius']='0'
        with patch('scripts.run_model_combination_benchmark.summarize_run',return_value=self.summary()):
            audited=collector(self.prepared,tampered,self.directory,manifest)
        self.assertEqual(audited['private_details'][0]['error_code'],'BENCHMARK_CAMPAIGN_SETTLEMENT_DIFFERS_FROM_RAW_AUDIT')
        self.assertEqual(audited['exposure_usd']['nebius'],'1.00')
        self.prepared['configs'][0]['settings_sha256']='b'*64
        with patch('scripts.run_model_combination_benchmark.summarize_run',return_value=self.summary()):
            report=collector(self.prepared,state,self.directory,manifest)
        group=next(g for g in report['accounting']['groups'] if g['modality']==job['modality'])
        self.assertEqual(group['audit_failed'],1);self.assertFalse(group['cost_complete'])
        self.assertEqual(group['held_usd']['openai'],'1.00')
        missing=self.directory/'nonexistent'
        report=collector(self.prepared,state,missing,manifest)
        self.assertEqual(report['private_details'][0]['status'],'AUDIT_FAIL_OR_UNRESOLVED')
        self.assertFalse(all(g['cost_complete'] for g in report['accounting']['groups']))

    def test_actual_wire_role_output_and_expiry_are_not_just_receipt_claims(self):
        target=self.directory/'wire';config=self.prepared['configs'][0]
        receipt=dict(route=self.route,cost_limit_usd='1.00',benchmark_expires_at=self.grant['expires_at'])
        self.save(target/'reviewed-settings/provider_stage_routing.json',dict(schema_version='1.0',route=self.route))
        row=dict(stage='twinpulse_semantic_structure',provider='nebius',model_id=config['roles']['planner']['model'],attempt_id='a'*32)
        path=target/'run-1/runtime/provider-evidence/dispatches'/('a'*32+'.json')
        wire=dict(request_redacted=json.dumps(dict(model=row['model_id'],max_tokens=20000)),started_at=self.now.isoformat())
        self.save(path,wire);summary=dict(rows=[row])
        audit_frozen_settings(receipt,config,summary,target,self.grant)
        wire['started_at']=self.grant['expires_at'];self.save(path,wire)
        with self.assertRaisesRegex(ValueError,'OUTSIDE_APPROVAL_WINDOW'):
            audit_frozen_settings(receipt,config,summary,target,self.grant)
        wire['started_at']=self.now.isoformat();wire['request_redacted']=json.dumps(dict(model=row['model_id'],max_tokens=8000))
        self.save(path,wire)
        with self.assertRaisesRegex(ValueError,'OUTPUT_POLICY_CHANGED'):
            audit_frozen_settings(receipt,config,summary,target,self.grant)

    def test_real_collector_cli_exports_only_metrics_and_cannot_overwrite_run_tree(self):
        state=initialize(self.prepared,self.grant)
        write_atomic(self.directory/'manifest-campaign.json',state,create=True)
        output=self.root/'derived-report';argv=['collector',str(self.directory),'--manifest',str(self.manifest),
            '--authorization',str(self.authorization),'--output',str(output)]
        before=(self.directory/'manifest-campaign.json').read_bytes()
        with patch.object(collect_cli.sys,'argv',argv),redirect_stdout(StringIO()),\
                patch('scripts.benchmark_campaign.subprocess.run',side_effect=AssertionError('NO_DISPATCH')):
            collect_cli.main()
            with self.assertRaises(FileExistsError):collect_cli.main()
        public=json.loads((output/'public-summary.json').read_text(encoding='utf-8'))
        private=json.loads((output/'private-collection.json').read_text(encoding='utf-8'))
        self.assertEqual(len(public['trials']),len(self.prepared['jobs']))
        self.assertTrue(all(not row['started'] for row in public['trials']));self.assertEqual(private['HTTP'],0)
        text=(output/'public-summary.json').read_text(encoding='utf-8')+(output/'public-summary.md').read_text(encoding='utf-8')
        for marker in ('ANSWER_ONLY_DO_NOT_SEND','answers.json',str(self.manifest),'An approximate space'):
            self.assertNotIn(marker,text)
        self.assertEqual((self.directory/'manifest-campaign.json').read_bytes(),before)
        argv[-1]=str(self.directory/'report')
        with patch.object(collect_cli.sys,'argv',argv):
            with self.assertRaisesRegex(ValueError,'MUST_NOT_CHANGE_RUN_TREE'):collect_cli.main()


if __name__=='__main__':unittest.main()
