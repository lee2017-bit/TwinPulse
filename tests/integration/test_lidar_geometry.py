# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import math
import unittest
from twinpulse_core.lidar_geometry import SectionIndex,slice_triangle


class LidarGeometryTests(unittest.TestCase):
    def test_height_slices_not_vertical_filled_boxes(self):
        self.assertEqual(slice_triangle([(1,-1,.7),(1,1,.7),(1,0,.9)],.182),[])
        section=slice_triangle([(1,-1,0),(1,1,0),(1,0,1)],.182)
        self.assertAlmostEqual(SectionIndex(section).cast((0,0),(1,0)),1)

    def test_leg_blocks_but_opening_under_table_does_not(self):
        index=SectionIndex([((1,.4),(1,.6)),((3,-2),(3,2))])
        self.assertEqual(index.cast((0,0),(1,0)),3)
        self.assertAlmostEqual(index.cast((0,.5),(1,0)),1)

    def test_nearest_hit_and_rotation(self):
        index=SectionIndex([((2,-2),(2,2)),((1,-2),(1,2))])
        self.assertEqual(index.cast((0,0),(1,0)),1)
        self.assertEqual(index.scan((0,0,math.pi/2),samples=4)[-1],[0.,-1.])

    def test_no_hit_is_not_fake_endpoint(self):
        self.assertEqual(SectionIndex([]).scan((0,0,0)),[])
        self.assertEqual(SectionIndex([((9,-1),(9,1))]).cast((0,0),(1,0)),8.)

    def test_coplanar_and_missing_height(self):
        self.assertEqual(len(slice_triangle([(0,0,.182),(1,0,.182),(0,1,.182)],.182)),3)
        self.assertEqual(slice_triangle([(0,0,0),(1,0,0),(0,1,0)],.182),[])

    def test_sensor_offset_changes_nearest_distance(self):
        index=SectionIndex([((1,-1),(1,1))])
        self.assertAlmostEqual(index.cast((-.032,0),(1,0)),1.032)

    def test_large_index_matches_brute_nearest(self):
        index=SectionIndex([((n,-1),(n,1)) for n in range(1,200)])
        self.assertEqual(index.cast((0,0),(1,0),200),1)


if __name__=='__main__':unittest.main()
