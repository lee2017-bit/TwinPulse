# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic files only; no robot or Isaac runtime."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_overnight_evidence import collect, digest, ESSENTIAL, FAKE, ISAAC, REQUIRED


class OvernightEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.reports = copy.deepcopy(REQUIRED)
        for name, paths in ESSENTIAL.items():
            hashes = {}
            for relative in paths:
                target = self.root/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('synthetic fixture', encoding='utf-8')
                hashes[relative] = digest(target)
            self.reports[name]['source_and_build_sha256'] = hashes
        self.save()

    def save(self):
        for name, value in self.reports.items():
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value), encoding='utf-8')

    def test_consistent_does_not_grant_physical_authority_or_claim_rerun(self):
        result = collect(self.root)
        self.assertEqual('PASS', result['status'])
        self.assertFalse(result['tests_rerun'])
        self.assertFalse(result['autonomous_robot_ready'])
        self.assertEqual('NOT_RUN', result['physical_validation'])

    def test_changed_or_missing_source_fails(self):
        target = self.root/next(iter(ESSENTIAL[FAKE]))
        target.write_text('changed', encoding='utf-8')
        self.assertEqual('FAIL', collect(self.root)['status'])
        target.unlink()
        self.assertEqual('FAIL', collect(self.root)['status'])

    def test_scope_boolean_cannot_be_replaced_with_zero(self):
        self.reports[ISAAC]['alignment_verified'] = 0
        self.save()
        self.assertEqual('FAIL', collect(self.root)['status'])

    def test_missing_hash_coverage_and_extra_dist_fail(self):
        self.reports[FAKE]['source_and_build_sha256'] = {}
        self.save()
        self.assertEqual('FAIL', collect(self.root)['status'])
        self.setUp()
        (self.root/'apps/twinpulse-web/dist/extra.js').write_text('new', encoding='utf-8')
        self.assertEqual('FAIL', collect(self.root)['status'])

    def test_conflicting_builds_fail(self):
        self.reports[FAKE]['source_and_build_sha256']['apps/twinpulse-web/dist/index.html'] = '0'*64
        self.save()
        result = collect(self.root)
        self.assertTrue(any('rehearsals disagree' in e for e in result['errors']))

    def test_duplicate_json_and_path_escape_fail(self):
        (self.root/FAKE).write_text('{"status":"FAIL","status":"PASS"}', encoding='utf-8')
        self.assertEqual('FAIL', collect(self.root)['status'])
        self.reports[FAKE]['source_and_build_sha256']['../outside'] = '0'*64
        self.save()
        self.assertEqual('FAIL', collect(self.root)['status'])


if __name__ == '__main__':
    unittest.main()
