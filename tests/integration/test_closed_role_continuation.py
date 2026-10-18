# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only current sealed prefix admission. No credentials/network/retries."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from scripts.benchmark_role_campaign import load_continuation,public_cases,validate_continuation_inventory,ROOT
from scripts.compare_model_roles_live import sha

class CurrentClosedPrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=ROOT/'outputs/benchmark-public-roles-20261011-v411b'
        cls.seal=ROOT/'outputs/benchmark-evidence-report-20261011-v412/closed-prefix-seal.json'
        if not cls.seal.exists():raise unittest.SkipTest('Local sealed campaign not shipped in public repository')
        spec=ROOT/'outputs/benchmark-overnight-20261011/dataset-spec.json'
        cls.cases=public_cases(json.loads(spec.read_text(encoding='utf-8')),spec)
        cls.carry=dict(nebius='3.05355147',openai='1.81365030')
        cls.held=['dc753cecf16d41898ed9777d2a6d14c0','3e120f4070164077b0700bbbdc3a19d1']
    def load(self,**changes):
        args=dict(root=self.root,audit_path=self.seal,audit_sha=sha(self.seal),
            acknowledged=self.held,cases=self.cases,carry=self.carry)
        args.update(changes);return load_continuation(**args)
    def test_exact_112_never_started_jobs_and_three_fixed_seeds(self):
        result=self.load();self.assertEqual(len(result['jobs']),112)
        self.assertEqual(result['reference']['skipped_started_jobs'],98)
        self.assertEqual(len(result['shared']),3)
        completed={r['job_id'] for r in result['history']}
        self.assertFalse(completed & {j['job_id'] for j in result['jobs']})
        validate_continuation_inventory(result,result['inventory'],result['scope']['jobs'],result['scope']['settings_hashes'])
    def test_both_holds_must_be_acknowledged(self):
        with self.assertRaisesRegex(ValueError,'ACKNOWLEDGEMENT'):self.load(acknowledged=self.held[:1])
    def test_no_refund_or_budget_reset(self):
        with self.assertRaisesRegex(ValueError,'CARRY_ALL_HOLDS'):self.load(carry=dict(nebius='3',openai='1.81365030'))
    def test_different_public_input_rejected(self):
        cases=deepcopy(self.cases);cases[0]['prompt']='different benchmark question'
        with self.assertRaisesRegex(ValueError,'INPUT_SETTINGS_OR_DEADLINE'):self.load(cases=cases)
    def test_seal_identity_required(self):
        with self.assertRaisesRegex(ValueError,'AUDIT_SHA_CHANGED'):self.load(audit_sha='wrong')

if __name__=='__main__':unittest.main()
