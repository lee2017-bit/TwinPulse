# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_native_scan import fixture
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_registration import propose_native_registration


def registration_fixture(sign=1, angle=.4, offset=(2., -1.)):
    data = fixture()
    data['frames'][0]['beams'] = [dict(angle_deg=a, distance_m=r, quality=100, node_index=i+10, source_byte_cursor=100+i)
                                 for i, (a, r) in enumerate([(0., 1.), (90., 1.5), (225., 1.2), (310., 2.)])]
    bundle = NativeScanBundle.from_dict(data)
    c, s = math.cos(angle), math.sin(angle)
    pairs = [{'node_index': p['node_index'], 'target_xy_m': [c*p['x_m']-s*sign*p['y_m']+offset[0],
                                                        s*p['x_m']+c*sign*p['y_m']+offset[1]]}
             for p in bundle.frame_preview(0)['points']]
    request = dict(schema_version='native-registration-request-1.0', bundle_digest=bundle.digest, frame_index=0,
                   target_frame='site_review_xy_m', scene_revision='c'*64, reference_kind='synthetic_test_fixture',
                   reference_sha256='d'*64, pairs=pairs)
    return bundle, request


class NativeRegistrationTests(unittest.TestCase):
    def test_both_conventions_separate_from_proper_rotation(self):
        for sign in (1, -1):
            for angle in (-math.pi, -.6, 0., 1.7, math.pi):
                with self.subTest(sign=sign, angle=angle):
                    bundle, request = registration_fixture(sign, angle)
                    before = bundle.to_dict()
                    result = propose_native_registration(bundle, request)
                    self.assertEqual(result['fit_status'], 'UNIQUE_CANDIDATE')
                    self.assertEqual(result['candidate_native_y_sign'], sign)
                    fitted = next(c for c in result['candidates'] if c['native_y_sign'] == sign)
                    self.assertAlmostEqual(fitted['rigid_transform']['x_m'], 2)
                    self.assertAlmostEqual(fitted['rigid_transform']['y_m'], -1)
                    self.assertAlmostEqual(math.cos(fitted['rigid_transform']['yaw_rad']), math.cos(angle))
                    self.assertAlmostEqual(fitted['max_residual_m'], 0)
                    self.assertEqual(fitted['rigid_transform']['rotation_determinant'], 1.)
                    self.assertEqual(bundle.to_dict(), before)
                    for key in ('motion_authorized', 'world_alignment_verified', 'sensor_to_base_verified', 'reference_bytes_verified'):
                        self.assertFalse(result[key])

    def test_no_scale_fitting_or_bad_pair_suppression(self):
        bundle, request = registration_fixture()
        for pair in request['pairs']:
            pair['target_xy_m'] = [x*2 for x in pair['target_xy_m']]
        result = propose_native_registration(bundle, request)
        self.assertEqual(result['fit_status'], 'NO_FIT')
        self.assertIsNone(result['candidate_native_y_sign'])
        self.assertTrue(all(len(c['residuals_m']) == 4 for c in result['candidates']))

    def test_binding_shapes_bounds_and_types(self):
        bundle, request = registration_fixture()
        changes = [('bundle_digest', 'e'*64), ('world_tf', {}), ('frame_index', True),
                   ('frame_index', 1), ('target_frame', 'world'), ('reference_kind', 'photo_guess'),
                   ('scene_revision', 'old'), ('reference_sha256', 'x'), ('reference_kind', 'operator_supplied_metric_reference')]
        for key, value in changes:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                propose_native_registration(bundle, dict(request, **{key: value}))
        for xy in ([True, 0], [float('nan'), 0], [101, 0], [0], '0,0'):
            bad = copy.deepcopy(request); bad['pairs'][0]['target_xy_m'] = xy
            with self.assertRaises(ValueError): propose_native_registration(bundle, bad)

    def test_missing_duplicate_invalid_samples_and_collinearity(self):
        bundle, request = registration_fixture()
        for pairs in (request['pairs'][:2], request['pairs'] * 5, [request['pairs'][0]] * 3):
            with self.assertRaises(ValueError): propose_native_registration(bundle, dict(request, pairs=pairs))
        bad = copy.deepcopy(request); bad['pairs'][0]['node_index'] = 999
        with self.assertRaises(ValueError): propose_native_registration(bundle, bad)
        bad = copy.deepcopy(request)
        for i, pair in enumerate(bad['pairs']): pair['target_xy_m'] = [i, 0]
        with self.assertRaises(ValueError): propose_native_registration(bundle, bad)

    def test_request_changes_invalidate_digest_and_copy_isolation(self):
        bundle, request = registration_fixture()
        original = propose_native_registration(bundle, request)
        self.assertEqual(original, propose_native_registration(bundle, request))
        changed = propose_native_registration(bundle, dict(request, scene_revision='f'*64))
        self.assertNotEqual(changed['proposal_digest'], original['proposal_digest'])
        original['candidates'].clear()
        self.assertEqual(len(propose_native_registration(bundle, request)['candidates']), 2)

if __name__ == '__main__': unittest.main()
