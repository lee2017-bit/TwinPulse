# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary numerical diagnostics, not photo/model acceptance."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

for package in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/package/'src'))
from twinpulse_provider.photo_layout import orientation_slot_diagnostics


class OrientationDiagnosticTests(unittest.TestCase):
    def item(self):
        return dict(id='worktop',kind='desk',dimensions_m=[1.2,.5,.75],
            yaw_deg=0,region='middle_right',variant='standard',finish='white')

    def run_diagnostic(self,item,placed,**kwargs):
        rows=[item];relations={'worktop':dict(relation='floor')}
        before=deepcopy((item,rows,relations,placed))
        result=orientation_slot_diagnostics(item,rows,relations,2.5,4,placed,
            parametric=True,**kwargs)
        self.assertEqual((item,rows,relations,placed),before)
        return result

    def test_quarter_turn_finds_strip_without_changing_original_or_accepting_it(self):
        # A synthetic occupied strip, not a photographed room or sensed pose.
        result=self.run_diagnostic(self.item(),[('blocker',-.4,0,(-.8,.8,-1.9,1.9))])
        self.assertEqual([r['yaw_deg'] for r in result],[90,-90])
        self.assertTrue(all(r['unblocked_candidate_count_lower_bound']>0 for r in result))
        self.assertTrue(all(r['physical_authority'] is False for r in result))
        self.assertTrue(all(r['acceptance'].startswith('NOT_VALIDATED') for r in result))

    def test_exhausted_sample_is_not_complete_or_infeasibility_proof(self):
        result=self.run_diagnostic(self.item(),[],max_points=1)
        self.assertTrue(all(r['tested_points']==1 and not r['sampling_complete'] for r in result))
        self.assertTrue(all(r['scope']=='FROZEN_PLACED_PROXIES_SAME_REGION_ONLY' for r in result))

    def test_factory_orientation_remains_restricted(self):
        item=self.item();item['kind']='rack'
        self.assertEqual(self.run_diagnostic(item,[]),[])

    def test_bound_and_frozen_blockers_remain_enforced(self):
        result=self.run_diagnostic(self.item(),[('blocker',0,0,(-2,2,-3,3))])
        self.assertTrue(all(r['unblocked_candidate_count_lower_bound']==0 for r in result))
        self.assertTrue(all(r['blocked_by_ids']==['blocker'] for r in result))
        with self.assertRaisesRegex(ValueError,'ORIENTATION_BUDGET_INVALID'):
            self.run_diagnostic(self.item(),[],max_points=True)


if __name__=='__main__':unittest.main()
