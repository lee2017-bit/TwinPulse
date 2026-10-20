# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Pure measured-profile validation. A digest is provenance, never calibration proof.

No default measurements, device imports, file reads or authority are created here.
The operator must supply and review measurements for this exact robot binding.
"""
from copy import deepcopy
from dataclasses import fields
import hashlib
import json
import math
import re
from control_timing import INPUT_TTL_S

try:
    from twinpulse_core.manual_motion_guard import NativeGeometry, SamplingModel, StopModel, ProgressThresholds
except ModuleNotFoundError:
    from manual_motion_guard import NativeGeometry, SamplingModel, StopModel, ProgressThresholds


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _shape(value, keys, code):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(code)


def profile_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def checked_profile(value, *, robot_id=None, binding_sha256=None):
    _shape(value, {'schema', 'robot_id', 'binding_sha256', 'geometry', 'sampling', 'timing', 'stop_model', 'progress'}, 'PROFILE_SHAPE')
    if (value['schema'] != 'physical-manual-profile-1.0'
            or not isinstance(value['robot_id'], str) or not re.fullmatch('[a-f0-9]{32}', value['robot_id'])
            or not _hash(value['binding_sha256'])):
        raise ValueError('PROFILE_IDENTITY')
    if robot_id is not None and value['robot_id'] != robot_id:
        raise ValueError('PROFILE_ROBOT_MISMATCH')
    if binding_sha256 is not None and value['binding_sha256'] != binding_sha256:
        raise ValueError('PROFILE_BINDING_MISMATCH')
    for name, kind in (('geometry', NativeGeometry), ('sampling', SamplingModel), ('stop_model', StopModel)):
        _shape(value[name], {f.name for f in fields(kind)} - {'provenance'}, 'PROFILE_' + name.upper() + '_SHAPE')
    g, s, t, p, progress = (value[k] for k in ('geometry', 'sampling', 'timing', 'stop_model', 'progress'))
    if (not isinstance(g['sensor_frame'], str) or not re.fullmatch('[A-Za-z0-9_/]{1,100}', g['sensor_frame'])
            or type(g['sensor_xy_yaw']) is not list or len(g['sensor_xy_yaw']) != 3
            or any(not _number(n, -math.pi, math.pi) for n in g['sensor_xy_yaw'])
            or type(g['native_angle_sign']) is not int or g['native_angle_sign'] not in (-1, 1)
            or not _hash(g['planar_extrinsic_sha256']) or not _hash(g['footprint_sha256'])):
        raise ValueError('PROFILE_MEASURED_GEOMETRY_REQUIRED')
    footprint = g['footprint_xy_m']
    if (type(footprint) is not list or not 3 <= len(footprint) <= 16
            or any(type(v) is not list or len(v) != 2 or any(not _number(n, -2, 2) for n in v)
                   or math.hypot(*v)>2 for v in footprint)):
        raise ValueError('PROFILE_FOOTPRINT_INVALID')
    for i, b in enumerate(footprint):
        a, c = footprint[i-1], footprint[(i+1) % len(footprint)]
        if (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]) <= 0:
            raise ValueError('PROFILE_FOOTPRINT_CONVEX_CCW_REQUIRED')
        if (c[0]-b[0])*(-b[1])-(c[1]-b[1])*(-b[0]) < 0:
            raise ValueError('PROFILE_FOOTPRINT_MUST_CONTAIN_ORIGIN')
        if any((c[0]-b[0])*(p[1]-b[1])-(c[1]-b[1])*(p[0]-b[0]) < -1e-10 for p in footprint):
            raise ValueError('PROFILE_FOOTPRINT_CONVEX_CCW_REQUIRED')
    if (not _number(s['minimum_range_m'], .000001, 65)
            or not _number(s['maximum_range_m'], s['minimum_range_m'], 65.535)
            or type(s['minimum_quality']) is not int or not 0 <= s['minimum_quality'] <= 255
            or not _number(s['maximum_gap_deg'], .000001, 45)
            or not _number(s['minimum_target_width_m'], .000001, 1)
            or not _number(s['range_uncertainty_m'], 0, 1)
            or not _hash(s['opaque_target_coverage_sha256'])):
        raise ValueError('PROFILE_MEASURED_SAMPLING_REQUIRED')
    _shape(t, {'maximum_pipeline_age_s', 'measurement_sha256', 'provenance'}, 'PROFILE_TIMING_SHAPE')
    if (t['provenance'] != 'measured' or not _number(t['maximum_pipeline_age_s'], .000001, .2)
            or not _hash(t['measurement_sha256'])):
        raise ValueError('PROFILE_MEASURED_PIPELINE_BOUND_REQUIRED')
    limits = {'body_clearance_m': (.1, 2), 'reaction_s': (0, 5),
              'minimum_linear_deceleration_m_s2': (.000001, 100), 'minimum_angular_deceleration_rad_s2': (.000001, 100),
              'linear_velocity_uncertainty_m_s': (0, 1), 'angular_velocity_uncertainty_rad_s': (0, 2),
              'position_uncertainty_m': (0, 1), 'maximum_scan_age_s': (.000001, .2),
              'maximum_input_age_s': (.000001, INPUT_TTL_S), 'maximum_linear_speed_m_s': (.000001, .05),
              'maximum_angular_speed_rad_s': (.000001, .30)}
    if any(not _number(p[k], *bounds) for k, bounds in limits.items()) or not _hash(p['stopping_measurement_sha256']):
        raise ValueError('PROFILE_MEASURED_STOP_MODEL_REQUIRED')
    extra = {'wheel_metres_per_tick', 'wheel_separation_m', 'body_progress_policy'}
    _shape(progress, {f.name for f in fields(ProgressThresholds)} - {'provenance'} | extra, 'PROFILE_PROGRESS_SHAPE')
    if (not _number(progress['window_s'], .05, 5)
            or not _number(progress['maximum_sample_gap_s'], .001, progress['window_s'])
            or not _number(progress['wheel_metres_per_tick'], .00000001, .01)
            or not _number(progress['wheel_separation_m'], .01, 2)
            or not _hash(progress['measurement_sha256'])
            or progress['body_progress_policy'] not in {'independent_required', 'explicitly_unverified_supervised'}):
        raise ValueError('PROFILE_MEASURED_PROGRESS_REQUIRED')
    for f in fields(ProgressThresholds):
        if f.name not in {'provenance', 'measurement_sha256', 'window_s', 'maximum_sample_gap_s'}:
            # Schema 1.0 keeps supplied historical measurements unchanged. Only
            # the explicitly wheel-only branch may leave unused body limits
            # unknown; null is never filled with a fabricated numeric default.
            if (f.name in {'minimum_body_translation_m','minimum_body_rotation_rad',
                           'maximum_body_speed_m_s','maximum_body_rotation_rad_s'}
                    and progress['body_progress_policy']=='explicitly_unverified_supervised'
                    and progress[f.name] is None):
                continue
            if not _number(progress[f.name], .000001, 10):
                raise ValueError('PROFILE_MEASURED_PROGRESS_REQUIRED')
    return deepcopy(value)


def profile_objects(value):
    value = checked_profile(value)
    geometry = dict(value['geometry'], provenance='measured')
    geometry['sensor_xy_yaw'] = tuple(geometry['sensor_xy_yaw'])
    geometry['footprint_xy_m'] = tuple(tuple(p) for p in geometry['footprint_xy_m'])
    progress = {f.name: value['progress'][f.name] for f in fields(ProgressThresholds) if f.name != 'provenance'}
    return (NativeGeometry(**geometry), SamplingModel(**value['sampling'], provenance='measured'),
            StopModel(**value['stop_model'], provenance='measured'), ProgressThresholds(**progress, provenance='measured'))
