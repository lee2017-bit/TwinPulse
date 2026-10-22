# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import math
import random
import subprocess
import sys
import textwrap
from pathlib import Path
import unittest
from twinpulse_core.lidar_geometry import SectionIndex,slice_triangle


class LidarGeometryTests(unittest.TestCase):
    def isolated(self,source):
        setup="import sys;sys.path.insert(0,sys.argv[1]);from twinpulse_core.lidar_geometry import SectionIndex\n"
        result=subprocess.run([sys.executable,'-I','-c',setup+textwrap.dedent(source),
            str(Path(__file__).resolve().parents[2]/'packages/twinpulse_core/src')],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_ray_releases_cancellation_owner_without_cyclic_gc_even_on_cancel(self):
        self.isolated('''
            import gc,weakref
            class Cancel:
                def __init__(self,stop):self.stop=stop
                def __call__(self):return self.stop
            enabled=gc.isenabled();gc.collect();gc.disable()
            try:
                index=SectionIndex([((1,-1),(1,1))])
                for stop in (False,True):
                    cancel=Cancel(stop);reference=weakref.ref(cancel)
                    if stop:
                        try:index.cast((0,0),(1,0),cancel=cancel)
                        except ValueError as e:assert str(e)=='LIDAR_SCAN_CANCELLED'
                        else:raise AssertionError('Cancellation must reject')
                    else:assert index.cast((0,0),(1,0),cancel=cancel)==1.
                    del cancel
                    assert reference() is None,'A completed ray leaves a self-referencing visit closure'
            finally:
                if enabled:gc.enable()
                gc.collect()
        ''')

    def test_index_build_does_not_leave_per_index_recursive_closure_cycles(self):
        self.isolated('''
            import gc
            from types import FunctionType
            enabled=gc.isenabled();gc.collect();gc.disable()
            try:
                for _ in range(30):SectionIndex([((1,-1),(1,1))])
                functions=[o for o in gc.get_objects() if isinstance(o,FunctionType)
                    and o.__qualname__=='SectionIndex.__init__.<locals>.build']
                assert not functions,'Index builder leaves recursive closure cycles'
            finally:
                if enabled:gc.enable()
                gc.collect()
        ''')

    def test_iterative_nearest_matches_independent_segment_intersections(self):
        rng=random.Random(1729)
        segments=[((rng.uniform(-4,4),rng.uniform(-4,4)),(rng.uniform(-4,4),rng.uniform(-4,4))) for _ in range(199)]
        index=SectionIndex(segments)
        for _ in range(300):
            origin=(rng.uniform(-2,2),rng.uniform(-2,2));angle=rng.uniform(-math.pi,math.pi)
            direction=(math.cos(angle),math.sin(angle));best=8.
            dx,dy=direction
            for a,b in segments:
                sx,sy=b[0]-a[0],b[1]-a[1];den=dx*sy-dy*sx
                if abs(den)<1e-12:continue
                ax,ay=a[0]-origin[0],a[1]-origin[1]
                t=(ax*sy-ay*sx)/den;u=(ax*dy-ay*dx)/den
                if 1e-7<t<best and -1e-9<=u<=1+1e-9:best=t
            self.assertAlmostEqual(index.cast(origin,direction),best,places=12)

    def test_empty_root_still_observes_cancel_before_none_and_hit_limit_is_strict(self):
        with self.assertRaisesRegex(ValueError,'LIDAR_SCAN_CANCELLED'):
            SectionIndex([]).cast((0,0),(1,0),cancel=lambda:True)
        self.assertEqual(SectionIndex([((8,-1),(8,1))]).scan((0,0,0),samples=1),[])

    def test_left_first_dfs_and_cancel_call_order_are_preserved(self):
        calls=[]
        class Node(tuple):
            def __new__(cls,label,values):
                value=super().__new__(cls,values);value.label=label;return value
            def __iter__(self):calls.append(self.label);return super().__iter__()
        index=SectionIndex([])
        left=Node('left',((1,-1,1,1),[((1,-1),(1,1))],None,None))
        right=Node('right',((2,-1,2,1),[((2,-1),(2,1))],None,None))
        index.root=Node('root',((1,-1,2,1),None,left,right))
        def cancel():calls.append('cancel');return False
        self.assertEqual(index.cast((0,0),(1,0),cancel=cancel),1.)
        self.assertEqual(calls,['cancel','root','cancel','left','cancel','right'])
        calls.clear()
        def stop():calls.append('cancel');return calls.count('cancel')>=3
        with self.assertRaisesRegex(ValueError,'LIDAR_SCAN_CANCELLED'):
            index.cast((0,0),(1,0),cancel=stop)
        self.assertEqual(calls,['cancel','root','cancel','left','cancel'])

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
