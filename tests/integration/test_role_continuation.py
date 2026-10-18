# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline continuation admission; no keys, network or model-performance claims."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.benchmark_role_campaign import load_continuation,validate_continuation_inventory,DEADLINE
from scripts.benchmark_protocol import canonical_sha
from scripts.compare_model_roles_live import sha


class RoleContinuationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.base=Path(self.folder.name);self.root=self.base/'prior';self.root.mkdir()
        self.cases=[dict(case_id='public-one',room_group='one',photo='fixture-not-sent',prompt='fixture')]
        self.jobs=[dict(job_id=str(i),case_id='public-one',role='observer' if i==0 else 'planner',
                       model_id='gpt-6-luna' if i==0 else 'nebius-fixture',repeat=1 if i<2 else 2) for i in range(3)]
        self.scope=dict(case_inputs=self.cases,jobs=self.jobs,expires_at=DEADLINE,settings_hashes={},
            existing_exposure_usd=dict(nebius='1',openai='1'),common_output_cap=40000,per_http_timeout_s=300,
            planner_request_cap=12,planner_repair_cap=3,planner_total_timeout_s=1800)
        self.write('scope.json',self.scope)
        self.inventory=dict(models=[dict(model_id='nebius-fixture',visible=True,context_tokens=100000)])
        self.write('inventory.json',self.inventory)
        self.write('progress/0001.json',{**self.jobs[0],'input_case':'public-one','case_id':'saved-observer','status':'PASS','actual_calls':1})
        self.write('public-one/cases/interrupted/start.json',dict(role='planner',model_id='nebius-fixture',repetition=1))
        self.write('public-one/cases/saved-observer/observation.json',dict(fixture=True))
        path=self.root/'public-one/cases/saved-observer/observation.json'
        self.write('public-one-shared-observation.json',dict(source_job_id='0',source_file_sha256=sha(path),
            sha256=canonical_sha(dict(fixture=True)),ground_truth=False))
        self.write('nebius.ledger.json',dict(requests=[dict(attempt_id='old-held',status='outcome_unknown',
            finished_at='fixture',charged_or_reserved_usd='.07')]))
        self.write('openai.ledger.json',dict(requests=[dict(attempt_id='old-received',status='received',
            finished_at='fixture',charged_or_reserved_usd='.01')]))
        self.carry=dict(nebius='1.07',openai='1.01')
        self.audit_path=self.base/'sealed-audit.json'
        self.audit=dict(schema_version='interrupted-public-role-audit-1.0',integrity_status='PASS',integrity_errors=[],
            stop_reasons=['INTERRUPTED_CAMPAIGN_NO_FINAL_REPORT','REMOTE_UNKNOWN_NEBIUS'],reported_cases=1,
            started_cases=2,planned=3,undispatched=1,financial={p:dict(total_exposure_usd=v) for p,v in self.carry.items()})
        self.seal()
        artifact=type('Artifact',(),{'to_dict':lambda unused:dict(fixture=True)})()
        self.mock=patch('scripts.benchmark_role_campaign.ObservationArtifact.from_mapping',return_value=artifact)
        self.mock.start();self.addCleanup(self.mock.stop)

    def write(self,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8')

    def seal(self):
        self.audit['original_files_sha256']={str(p.relative_to(self.root)):sha(p) for p in self.root.rglob('*') if p.is_file()}
        self.audit_path.write_text(json.dumps(self.audit),encoding='utf-8')
        self.audit_sha=sha(self.audit_path)

    def load(self,**kwargs):
        values=dict(root=self.root,audit_path=self.audit_path,audit_sha=self.audit_sha,
                    acknowledged=['old-held'],cases=self.cases,carry=self.carry)
        values.update(kwargs);return load_continuation(**values)

    def test_only_undispatched_job_and_identical_shared_observation(self):
        value=self.load()
        self.assertEqual(value['jobs'],self.jobs[2:])
        self.assertEqual(value['reference']['skipped_interrupted_job'],self.jobs[1])
        self.assertFalse(value['reference']['prior_scores_merged'])
        self.assertTrue(value['reference']['new_unknown_stops'])
        self.assertEqual(value['shared']['public-one'].to_dict(),dict(fixture=True))

    def test_all_held_spend_must_carry_no_budget_reset(self):
        with self.assertRaisesRegex(ValueError,'CARRY_ALL_HOLDS'):
            self.load(carry=dict(nebius='1',openai='1.01'))

    def test_acknowledgement_only_named_old_unknown_not_new_unknown(self):
        with self.assertRaisesRegex(ValueError,'ACKNOWLEDGEMENT'):
            self.load(acknowledged=[])
        with self.assertRaisesRegex(ValueError,'ACKNOWLEDGEMENT'):
            self.load(acknowledged=['old-held','new-unknown'])

    def test_original_or_audit_change_rejected(self):
        self.write('scope.json',dict(changed=True))
        with self.assertRaisesRegex(ValueError,'ORIGINAL_CHANGED'):self.load()
        with self.assertRaisesRegex(ValueError,'AUDIT_SHA_CHANGED'):self.load(audit_sha='wrong')

    def test_active_or_foreign_locks_not_deleted(self):
        for name in ('owner.lock','nebius.ledger.dispatch-lock'):
            with self.subTest(name=name):
                path=self.root/name;path.write_text('foreign',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'LOCK'):self.load()
                self.assertEqual(path.read_text(encoding='utf-8'),'foreign')
                path.unlink()  # test-owned fixture only

    def test_pending_old_http_cannot_be_acknowledged(self):
        self.write('nebius.ledger.json',dict(requests=[dict(attempt_id='old-held',status='outcome_unknown',charged_or_reserved_usd='.07')]))
        self.seal()
        with self.assertRaisesRegex(ValueError,'STILL_PENDING'):self.load()

    def test_input_cap_deadline_or_schedule_cannot_change(self):
        for key,value in (('common_output_cap',20000),('expires_at','2099-01-01')):
            self.scope[key]=value;self.write('scope.json',self.scope);self.seal()
            with self.assertRaises(ValueError):self.load()
            self.scope[key]=40000 if key=='common_output_cap' else DEADLINE
        self.scope['jobs'][0]['job_id']='changed';self.write('scope.json',self.scope);self.seal()
        with self.assertRaisesRegex(ValueError,'ORDER'):self.load()

    def test_no_fabricated_interrupted_result_or_ground_truth_seed(self):
        self.write('public-one/cases/interrupted/result.json',dict(status='PASS'));self.seal()
        with self.assertRaisesRegex(ValueError,'INTERRUPTION_AMBIGUOUS'):self.load()

    def test_current_inventory_schedule_and_settings_identical(self):
        value=self.load()
        validate_continuation_inventory(value,self.inventory,self.jobs,{})
        reordered=deepcopy(list(reversed(self.jobs)))
        for index,row in enumerate(reordered):row['position']=index
        validate_continuation_inventory(value,self.inventory,reordered,{})
        self.assertEqual(value['jobs'],self.jobs[2:])
        other=deepcopy(self.inventory);other['models'][0]['context_tokens']=200000
        with self.assertRaisesRegex(ValueError,'CATALOG_CHANGED'):validate_continuation_inventory(value,other,self.jobs,{})
        with self.assertRaisesRegex(ValueError,'SCHEDULE_CHANGED'):validate_continuation_inventory(value,self.inventory,self.jobs[1:],{})
        with self.assertRaisesRegex(ValueError,'SETTINGS_IDENTITY'):validate_continuation_inventory(value,self.inventory,self.jobs,{'foreign':'sha'})


if __name__=='__main__':unittest.main()
