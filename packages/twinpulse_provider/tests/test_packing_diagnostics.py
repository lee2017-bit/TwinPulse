# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic grid oracles and budget causes; no measured-room answer data."""
from copy import deepcopy
from itertools import product
import unittest

from twinpulse_provider.photo_layout import _bounded_region_repack


class PackingDiagnosticTests(unittest.TestCase):
    def rows(self, count=2):
        return [dict(id='item'+str(i),region='middle_centre') for i in range(count)]

    def test_grid_exhaustion_agrees_with_independent_small_oracle(self):
        # .9m squares in 1.4m floor: .11m margin leaves nine grid centres.
        points=list(product((-.14,-.1,0.,.1,.14),repeat=2))
        oracle=any(abs(a[0]-b[0])>=.93 or abs(a[1]-b[1])>=.93
                   for a,b in product(points,repeat=2))
        self.assertFalse(oracle)
        rows=self.rows();before=deepcopy(rows)
        found,report=_bounded_region_repack(rows,lambda _:(.9,.9),1.4,1.4,branch_cap=1000)
        self.assertIsNone(found)
        self.assertEqual(report['termination_code'],'GRID_SEARCH_EXHAUSTED')
        self.assertTrue(report['grid_search_exhaustive'])
        self.assertEqual(report['domain_counts'],{'item0':25,'item1':25})
        self.assertEqual(rows,before)

    def test_same_problem_with_truncated_branches_is_not_exhaustive(self):
        _,report=_bounded_region_repack(self.rows(),lambda _:(.9,.9),1.4,1.4,branch_cap=1)
        self.assertEqual(report['termination_code'],'BRANCH_BUDGET_EXHAUSTED')
        self.assertFalse(report['grid_search_exhaustive'])
        self.assertGreater(report['branches_truncated'],0)

    def test_node_budget_is_not_geometry_infeasibility(self):
        _,report=_bounded_region_repack(self.rows(),lambda _:(.9,.9),1.3,1.3,max_nodes=1)
        self.assertEqual(report['termination_code'],'NODE_BUDGET_EXHAUSTED')
        self.assertFalse(report['grid_search_exhaustive'])

    def test_time_budget_identifies_domain_and_search_phase(self):
        for width,phase in ((12.,'domain_generation'),(1.3,'backtracking')):
            values=iter((0.,1.,1.))
            _,report=_bounded_region_repack(self.rows(),lambda _:(.9,.9),width,width,
                timeout_s=.5,clock=lambda:next(values))
            self.assertEqual(report['termination_code'],'TIME_BUDGET_EXHAUSTED')
            self.assertEqual(report['phase'],phase)
            self.assertFalse(report['grid_search_exhaustive'])

    def test_empty_domain_and_success_are_distinct(self):
        _,report=_bounded_region_repack(self.rows(1),lambda _:(1.,1.),.3,.3)
        self.assertEqual(report['termination_code'],'EMPTY_DOMAIN')
        found,report=_bounded_region_repack(self.rows(1),lambda _:(.9,.9),1.3,1.3)
        self.assertEqual(found,{'item0':(0.,0.)})
        self.assertEqual(report['termination_code'],'FOUND')
        self.assertFalse(report['physical_authority'])

    def test_empty_grid_does_not_prove_continuous_geometry_infeasible(self):
        # A continuous centre at (-.06,-.06) fits the .11m floor margin and
        # front-left region, but no 10cm lattice point fits. No global claim.
        self.assertLess(.06+.45/2+.11,.8/2)
        found,report=_bounded_region_repack([dict(id='small',region='front_left')],
            lambda _:(.45,.45),.8,.8)
        self.assertEqual(report['termination_code'],'FOUND')
        self.assertTrue(found)
        x,y=found['small']
        self.assertLessEqual(abs(x)+.45/2+.11,.8/2+1e-12)
        self.assertLessEqual(abs(y)+.45/2+.11,.8/2+1e-12)
        self.assertLessEqual(x,-.05);self.assertLessEqual(y,-.05)
        self.assertFalse(report['grid_search_exhaustive'])
        self.assertFalse(report['global_infeasibility_proved'])

    def test_invalid_budget_rejected(self):
        for kwargs in ({'max_nodes':-1},{'branch_cap':0},{'timeout_s':float('nan')}):
            with self.assertRaisesRegex(ValueError,'SEARCH_BUDGET_INVALID'):
                _bounded_region_repack(self.rows(),lambda _:(.9,.9),1.3,1.3,**kwargs)


if __name__=='__main__':unittest.main()
