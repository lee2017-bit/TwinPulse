# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit native sample correspondences -> bounded 2D registration candidates.

Pure proposal math, not calibration certification. Both native angular conventions
are evaluated, with conversion sign separated from the proper rigid rotation.
No guessed room dimensions, scaling, automatic nearest-neighbour matching, TF
timestamp fabrication, map edits, or execution authority.
"""
import itertools
import math

from .native_scan import NativeScanBundle, _shape, _digest, _integer, _number
from .revisions import canonical_sha256

MAX_RESIDUAL_M = .05  # Draft fit threshold, never a physical safety tolerance.
MIN_TRIANGLE_AREA_M2 = .01  # Conditioning guard for chirality discrimination.


def _area(points):
    return max(abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
               for a, b, c in itertools.combinations(points, 3))


def propose_native_registration(bundle: NativeScanBundle, request: dict) -> dict:
    checked = NativeScanBundle.from_text(bundle._json)
    _shape(request, 'schema_version bundle_digest frame_index target_frame scene_revision reference_kind reference_sha256 pairs')
    if request['schema_version'] != 'native-registration-request-1.0':
        raise ValueError('unsupported native registration version')
    if request['bundle_digest'] != checked.digest:
        raise ValueError('registration belongs to different saved evidence')
    for key in ('scene_revision', 'reference_sha256'):
        _digest(request[key])
    if request['target_frame'] != 'site_review_xy_m':
        raise ValueError('registration target must be the explicit metric site-review frame')
    if request['reference_kind'] not in ('synthetic_test_fixture', 'operator_supplied_metric_reference'):
        raise ValueError('independent metric reference required; photo/display guesses unsupported')
    if (checked.to_dict()['source']['kind'] == 'synthetic_test_fixture'
            and request['reference_kind'] != 'synthetic_test_fixture'):
        raise ValueError('synthetic recording cannot become physical reference evidence')
    preview = checked.frame_preview(request['frame_index'])
    original = {p['node_index']: p for p in preview['points']}
    pairs = request['pairs']
    if type(pairs) is not list or not 3 <= len(pairs) <= 16:
        raise ValueError('provide 3..16 noncollinear, explicit original sample correspondences')
    native, target, seen = [], [], set()
    for pair in pairs:
        _shape(pair, 'node_index target_xy_m')
        _integer(pair['node_index'], 0, 200000)
        node = pair['node_index']
        if node in seen or node not in original:
            raise ValueError('duplicate, invalid or other-frame native sample')
        seen.add(node)
        xy = pair['target_xy_m']
        if type(xy) is not list or len(xy) != 2:
            raise ValueError('target point must have two SI metre coordinates')
        for value in xy: _number(value, -100, 100)
        native.append((original[node]['x_m'], original[node]['y_m']))
        target.append(tuple(xy))
    if min(_area(native), _area(target)) < MIN_TRIANGLE_AREA_M2:
        raise ValueError('reference geometry is collinear or too small to distinguish handedness')
    candidates = []
    tx, ty = [sum(p[i] for p in target) / len(target) for i in (0, 1)]
    for sign in (1, -1):
        converted = [(x, sign * y) for x, y in native]
        sx, sy = [sum(p[i] for p in converted) / len(converted) for i in (0, 1)]
        dot = sum((p[0]-sx)*(q[0]-tx) + (p[1]-sy)*(q[1]-ty) for p, q in zip(converted, target))
        cross = sum((p[0]-sx)*(q[1]-ty) - (p[1]-sy)*(q[0]-tx) for p, q in zip(converted, target))
        if math.hypot(dot, cross) < 1e-12:
            candidates.append({'native_y_sign': sign, 'rigid_transform': None, 'fit_pass': False,
                               'reason': 'degenerate_rotation_covariance', 'max_residual_m': None,
                               'rms_residual_m': None, 'residuals_m': []})
            continue
        angle = math.atan2(cross, dot)
        c, s = math.cos(angle), math.sin(angle)
        dx, dy = tx - c*sx + s*sy, ty - s*sx - c*sy
        residuals = [math.hypot(c*p[0]-s*p[1]+dx-q[0], s*p[0]+c*p[1]+dy-q[1])
                     for p, q in zip(converted, target)]
        candidates.append({'native_y_sign': sign,
                           'rigid_transform': {'x_m': dx, 'y_m': dy, 'yaw_rad': angle, 'rotation_determinant': 1.0},
                           'fit_pass': max(residuals) <= MAX_RESIDUAL_M, 'reason': 'residual_evaluated',
                           'max_residual_m': max(residuals),
                           'rms_residual_m': math.sqrt(sum(r*r for r in residuals)/len(residuals)),
                           'residuals_m': residuals})
    passing = [c['native_y_sign'] for c in candidates if c['fit_pass']]
    result = {'schema_version': 'native-registration-proposal-1.0', 'bundle_digest': checked.digest,
              'frame_index': request['frame_index'], 'scene_revision': request['scene_revision'],
              'target_frame': request['target_frame'], 'reference_kind': request['reference_kind'],
              'reference_sha256': request['reference_sha256'], 'reference_bytes_verified': False,
              'request_digest': canonical_sha256(request), 'sample_indices': [p['node_index'] for p in pairs],
              'candidates': candidates, 'max_residual_threshold_m': MAX_RESIDUAL_M,
              'fit_status': 'UNIQUE_CANDIDATE' if len(passing) == 1 else 'AMBIGUOUS' if passing else 'NO_FIT',
              'candidate_native_y_sign': passing[0] if len(passing) == 1 else None,
              'world_alignment_verified': False, 'sensor_to_base_verified': False,
              'physical_validation': 'NOT_RUN', 'motion_authorized': False,
              'notice': 'Fit to supplied metric references only. Reference identity, native convention and sensor/base/world relationship require independent validation. No TF or navigation approval.'}
    result['proposal_digest'] = canonical_sha256(result)
    return result
