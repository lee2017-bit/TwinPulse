# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic phase regressions, not a real-model/user acceptance substitute."""
from pathlib import Path
import sys
import unittest
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[3]
for name in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core.geometry_checks import GeometryChecks
from twinpulse_provider.generation_policy import ProgressTracker
from twinpulse_provider.errors import ProviderConfigurationError


def ledger(rev, **statuses):
    checks=GeometryChecks(rev,'compiler','library',['example'])
    for row in checks.rows:row['status']=statuses.get(row['check_id'],'passed')
    return checks.report()|{'issues':[]}


class PartialProgressTests(unittest.TestCase):
    def test_partial_is_valid_unfinished_and_protects_passed_floor(self):
        t=ProgressTracker()
        partial=ledger('a'*64,support_packing='partial')
        self.assertFalse(t.observe({'value':1},[],partial))
        self.assertEqual(t.decision,'initial')
        self.assertFalse(partial['checks_complete'])
        self.assertEqual(t.best_checks['support_packing']['status'],'partial')
        bad=ledger('b'*64,floor_packing='failed',support_packing='blocked')
        self.assertFalse(t.observe({'value':2},['PHOTO_LAYOUT_REGION_FULL'],bad))
        self.assertTrue(t.regressed)
        self.assertEqual(t.best_checks['floor_packing']['status'],'passed')

    def test_passed_to_partial_is_regression_not_success(self):
        t=ProgressTracker();t.observe({'value':1},[],ledger('a'*64))
        t.observe({'value':2},[],ledger('b'*64,support_packing='partial'))
        self.assertTrue(t.regressed)
        self.assertFalse(t.advanced_checks)

    def test_old_baseline_rebind_preserves_seen_history_and_requires_fresh_evidence(self):
        t=ProgressTracker();t.observe({'value':1},['old'],ledger('a'*64,floor_packing='failed'))
        seen=set(t.seen);history=deepcopy(t.history)
        partial=ledger('b'*64,support_packing='partial')
        t.rebind_locally_checked_best({'value':2},partial)
        self.assertTrue(seen <= t.seen)
        self.assertEqual(t.history[:len(history)],history)
        self.assertFalse(t.history[-1]['checks_complete'])
        with self.assertRaises(ProviderConfigurationError):
            t.rebind_locally_checked_best({'value':3},ledger('c'*64,floor_packing='failed'))
