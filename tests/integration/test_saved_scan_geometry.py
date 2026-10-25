# SPDX-License-Identifier: Apache-2.0
"""Offline geometry/estimator regressions, never physical acceptance."""
import math
import time
import unittest
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))

from twinpulse_core.environment_section import horizontal_section,matching_outline
from twinpulse_app.scan_fit_diagnostics import uniform_ring, segment_fit
from tests.integration.test_environment_import import source


def room_scan(x=0.,y=0.,yaw=0.,count=400):
    result=[]
    for i in range(count):
        a=i*math.tau/count+yaw;c=math.cos(a);s=math.sin(a);ranges=[]
        if abs(c)>1e-9:ranges.append(((3.-x) if c>0 else (-1.-x))/c)
        if abs(s)>1e-9:ranges.append(((1.5-y) if s>0 else (-2.-y))/s)
        d=min(ranges);b=i*math.tau/count;result.append([d*math.cos(b),d*math.sin(b)])
    return result


class SavedGeometryTests(unittest.TestCase):
    def test_sampling_covers_full_ring_and_does_not_mutate_source(self):
        points=[[i,0.] for i in range(398)];original=deepcopy(points)
        sampled=uniform_ring(points,120)
        self.assertEqual(len(sampled),120);self.assertGreater(sampled[-1][0],393)
        self.assertEqual(len({p[0] for p in sampled}),120);self.assertEqual(points,original)
        self.assertEqual(uniform_ring(points[:3],120),points[:3])

    def test_ray_resampling_recovers_translation_not_just_copied_point_pairs(self):
        for dx,dy,yaw in ((.1,0.,0.),(-.1,0.,0.),(.03,.02,.03)):
            with self.subTest(dx=dx,dy=dy,yaw=yaw):
                fit=segment_fit(room_scan(),room_scan(dx,dy,yaw),deadline=time.monotonic()+4)
                self.assertAlmostEqual(fit['delta'][0],dx,delta=.003)
                self.assertAlmostEqual(fit['delta'][1],dy,delta=.003)
                self.assertAlmostEqual(fit['delta'][2],yaw,delta=.003)
                self.assertTrue(fit['converged']);self.assertLess(fit['residual_m'],.003)
                self.assertFalse(fit['physical_motion_verified'])

    def test_scan_order_and_clockwise_ring_do_not_change_fit(self):
        before=room_scan();after=room_scan(.1)
        shifted=after[91:]+after[:91]
        fit=segment_fit(before[::-1],shifted,deadline=time.monotonic()+4)
        self.assertAlmostEqual(fit['delta'][0],.1,delta=.003)

    def test_single_wall_or_deadline_is_not_a_pose_measurement(self):
        with self.assertRaises(ValueError):
            segment_fit([[i*.01,1.] for i in range(120)],[[i*.01,1.1] for i in range(120)],deadline=time.monotonic()+3)
        with self.assertRaisesRegex(ValueError,'DEADLINE'):
            segment_fit(room_scan(),room_scan(.1),deadline=time.monotonic()-1)

    def test_expiry_during_final_residual_cannot_publish_a_fit(self):
        square_root=math.sqrt;completed=[]
        def residual(value):
            completed.append(value);return square_root(value)
        with patch('twinpulse_app.scan_fit_diagnostics.time.monotonic',side_effect=lambda:2. if len(completed)>=3 else 0.), \
                patch('twinpulse_app.scan_fit_diagnostics.math.sqrt',side_effect=residual):
            with self.assertRaisesRegex(ValueError,'DEADLINE'):
                segment_fit(room_scan(),room_scan(.1),deadline=1.)
        self.assertEqual(len(completed),3)

    def test_section_uses_translated_triangles_not_aabb_solid(self):
        env=source();wall=deepcopy(env['meshes'][1]);wall.update(category='wall',label='Wall0',translation_m=[0.,0.,0.],
            points_m=[[0.,0.,0.],[2.,2.,0.],[2.,2.,2.],[0.,0.,2.]],triangles=[[0,1,2],[0,2,3]])
        env['meshes'][1]=wall;original=deepcopy(env)
        result=horizontal_section(env,.18)
        self.assertTrue(result['segments']);self.assertEqual(result['source_sha256'],env['source_sha256'])
        for segment in result['segments']:
            for x,y in segment['ends_m']:self.assertAlmostEqual(x,y)
        self.assertEqual(env,original)
        # A single wall's two cut segments are not enough geometry for the
        # matcher adapter; do not pad the fixture with fake localization walls.
        with self.assertRaisesRegex(ValueError,'SECTION_MATCH_SEGMENT_BUDGET'):
            matching_outline(env,.18)

    def test_section_omits_objects_outside_sensor_height_and_preserves_openings(self):
        env=source();chair=env['meshes'][1]
        self.assertEqual(horizontal_section(env,.18)['segments'],[])
        # Two separated jambs must not become one room-spanning box edge.
        chair.update(points_m=[[0.,0.,0.],[0.,1.,0.],[0.,1.,1.],[0.,2.,0.],[0.,3.,0.],[0.,3.,1.]],
            triangles=[[0,1,2],[3,4,5]],translation_m=[.1,.2,0.])
        segments=horizontal_section(env,.18)['segments']
        self.assertEqual(len(segments),2)
        self.assertTrue(all(max(p[1] for p in s['ends_m'])-min(p[1] for p in s['ends_m'])<1.01 for s in segments))
        self.assertTrue(all(abs(p[0]-.1)<1e-9 for s in segments for p in s['ends_m']))
        for bad in (-1.,float('nan'),True):
            with self.assertRaises(ValueError):horizontal_section(env,bad)


if __name__=='__main__':unittest.main()
