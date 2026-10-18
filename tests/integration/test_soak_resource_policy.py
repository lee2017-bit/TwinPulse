# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure verifier policy tests, never substitutes for actual wall-time soak."""
from copy import deepcopy
import unittest
from scripts.verify_goal_separated_journey import soak_resource_summary


class SoakPolicyTests(unittest.TestCase):
    def samples(self):
        return [{'soak_active':True,'artifact_bytes':100+i,
            'owned_children':{name:{'private_bytes':1024**3+i*1024}
                for name in ('backend','browser','engine')}} for i in range(120)]

    def test_complete_small_range_reports_every_process_and_accepts(self):
        value=soak_resource_summary(self.samples())
        self.assertTrue(value['accepted']);self.assertEqual(value['samples'],120)
        self.assertEqual(set(value['summary']),{'backend','browser','engine'})
        self.assertEqual(value['physical_validation'],'NOT_RUN')

    def test_exceeded_budgets_are_retained_not_skipped_or_relaxed(self):
        rows=self.samples()
        for name in ('backend','browser','engine'):rows[-1]['owned_children'][name]['private_bytes']+=2*1024**3
        value=soak_resource_summary(rows)
        self.assertFalse(value['accepted']);self.assertEqual(len(value['rejection_codes']),3)
        self.assertEqual(value['summary']['browser']['range_budget_bytes'],256*1024**2)

    def test_insufficient_coverage_is_not_pass(self):
        with self.assertRaisesRegex(ValueError,'SOAK_RESOURCE_COVERAGE_REQUIRED'):
            soak_resource_summary(self.samples()[:109])

    def test_warmup_and_nonactive_rows_are_not_mistaken_for_settled_growth(self):
        rows=self.samples();warmup=deepcopy(rows[0]);warmup['soak_active']=False
        for name in warmup['owned_children']:warmup['owned_children'][name]['private_bytes']=10*1024**3
        for row in rows[:4]:
            for name in row['owned_children']:row['owned_children'][name]['private_bytes']=8*1024**3
        self.assertTrue(soak_resource_summary([warmup]+rows)['accepted'])
