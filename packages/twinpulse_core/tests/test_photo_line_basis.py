# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import math
import unittest
from twinpulse_core.automatic_photo_alignment import _same_line_basis,stable_lines


class PhotoLineBasisTests(unittest.TestCase):
    def test_basis_flip_preserves_endpoints_exactly(self):
        row={'n':[0.,-1.],'t':[-1.,0.],'rho':-2.,'lo':-3.,'hi':1.,'error':.01}
        changed=_same_line_basis(row,[0.,1.])
        def ends(r):return sorted(tuple(r['n'][j]*r['rho']+r['t'][j]*s for j in range(2)) for s in (r['lo'],r['hi']))
        self.assertEqual(ends(row),ends(changed));self.assertEqual(row['rho'],-2.)
        self.assertEqual(changed['error'],row['error'])
        self.assertIs(_same_line_basis(row,[0.,-1.]),row)

    def test_small_axis_crossing_noise_is_one_supported_wall_not_two_under_supported_groups(self):
        views=[]
        for i,slope in enumerate((.001,-.001,.002,-.002)):
            origin=[i*.1,i*.04,0.]
            points=[[x-origin[0],1+slope*x-origin[1]] for x in [j/20 for j in range(-20,21)]]
            views.append({'sequence':i,'pose':origin,'points':points})
        lines=stable_lines(views)
        self.assertEqual(len(lines),1);self.assertEqual(len(lines[0]['support_sequences']),4)
        self.assertLess(abs(abs(lines[0]['rho'])-1),.003)

    def test_parallel_distinct_walls_and_insufficient_support_stay_separate(self):
        views=[]
        for i,slope in enumerate((.001,-.001,.002,-.002)):
            origin=[i*.1,i*.04,0.]
            first=[[x-origin[0],1+slope*x-origin[1]] for x in [j/20 for j in range(-20,21)]]
            second=[[x-origin[0],1.2+slope*x-origin[1]] for x in [j/20 for j in range(20,-21,-1)]]
            # Gap exceeds the unchanged adjacency gate; no inferred bridge.
            views.append({'sequence':i,'pose':origin,'points':first+[[8,8]]+second})
        lines=stable_lines(views);self.assertEqual(len(lines),2)
        self.assertGreater(abs(lines[0]['rho']-lines[1]['rho']),.15)
        self.assertEqual(stable_lines(views[:2]),[])


if __name__=='__main__':unittest.main()
