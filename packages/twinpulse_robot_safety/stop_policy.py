# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Versioned low-speed supervised commissioning policy, NOT a safety certification.

Nominal encoder wheel travel is not chassis displacement (slip is unobserved).
Policy rationale/limits: docs/verification/manual-stop-policy-v2-20260927.md.
No ROS, network, device access, receipt creation, or tunable client thresholds.
"""
import hashlib
import json
import math

POLICY = {
    'id': 'supervised-stop-2.1',
    'wheel_radius_mm': 33., 'ticks_per_revolution': 4096,
    'guard_observation_limit_s': .7,
    'deceleration_budget_s': .5, 'verification_s': .3,
    'wheel_travel_limit_mm': 10., 'residual_rate_limit_mm_s': 1.,
    'max_sample_gap_s': .1, 'max_source_age_s': .2,
    'scope': 'observed_flat_clear_floor_linear_0.05_angular_0.30',
}
POLICY_SHA256 = hashlib.sha256(json.dumps(POLICY, sort_keys=True).encode()).hexdigest()
MM_PER_TICK = 2 * math.pi * POLICY['wheel_radius_mm'] / POLICY['ticks_per_revolution']
OBSERVE_S = POLICY['deceleration_budget_s'] + POLICY['verification_s']
# Motion progress sampling may be configured more coarsely. Stop evidence
# still requires dense samples within the existing 300ms verification window.
FIELD_STOP_SAMPLE_GAP_CAP_S = .225


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def field_stop_policy(timing_values):
    """Separate engineering coverage, never a legacy stop qualification."""
    from twinpulse_core.robot_timing_profile import checked_values, digest
    values=checked_values(timing_values)
    gap=values['wheel_interval_ms']/1000
    # Do not reject a wider motion interval before observing the actual stop.
    # Nor may that wider setting certify a sparsely observed stop as PASS.
    coverage_gap=min(gap,FIELD_STOP_SAMPLE_GAP_CAP_S)
    cutoff_limit=max(POLICY['guard_observation_limit_s'],values['output_timeout_ms']/1000+.25)
    return dict(POLICY,id='supervised-field-stop-coverage-1.1',max_sample_gap_s=coverage_gap,
        motion_sample_gap_s=gap,stop_sample_gap_cap_s=FIELD_STOP_SAMPLE_GAP_CAP_S,
        guard_observation_limit_s=cutoff_limit,
        scope='engineering_forward_wheel_observation_not_legacy_qualification',
        coverage_basis='PINNED_SENSORSTATE_WHEEL_INTERVAL_NOT_ODOMETRY',
        timing_values_sha256=digest(values))


def assess_field_stop(rows, timeout_s, last_send_s, timing_values):
    return _assess_stop(rows,timeout_s,last_send_s,field_stop_policy(timing_values))


def assess_stop(rows, timeout_s, last_send_s):
    return _assess_stop(rows,timeout_s,last_send_s,POLICY)


def _assess_stop(rows, timeout_s, last_send_s, policy):
    """Independent cutoff/coverage/travel/residual results; no extrapolated samples.

Both wheel paths use absolute increments so reversal cannot cancel travel.
Final verification is a fixed window AFTER the deceleration budget, not
an anchor reset timer competing for that same budget. Bracketing real samples
must cover every boundary. OFF/cleanup samples cannot qualify a torque-on stop.
"""
    result = {'policy_id': policy['id'], 'policy_sha256': hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest(),
              'status': 'INCOMPLETE', 'checks': {}, 'metrics': {},
              'limits': dict(policy), 'chassis_stop': 'NOT_MEASURED'}
    checks, metrics = result['checks'], result['metrics']
    if not finite(timeout_s) or not finite(last_send_s):
        result['reason'] = 'STOP_TIMESTAMPS_INVALID'
        return result
    delay = timeout_s - last_send_s
    metrics['guard_observation_ms'] = delay * 1000
    checks['command_cutoff_observed'] = 0 <= delay <= policy['guard_observation_limit_s']
    if not checks['command_cutoff_observed']:
        result.update(status='FAIL', reason='COMMAND_CUTOFF_LATE')
        return result
    if not isinstance(rows, list) or not 2 <= len(rows) <= 10000:
        result['reason'] = 'SENSOR_COVERAGE_INVALID'
        return result
    previous = None
    for row in rows:
        if not isinstance(row, dict) or not finite(row.get('t')):
            result['reason'] = 'SENSOR_SHAPE_INVALID'
            return result
        enc = row.get('encoders')
        if (not isinstance(enc, list) or len(enc) != 2
                or any(type(e) is not int or not -(2**31) <= e < 2**31 for e in enc)
                or (previous is not None and row['t'] <= previous)):
            result['reason'] = 'SENSOR_SHAPE_INVALID'
            return result
        previous = row['t']
    end = timeout_s + OBSERVE_S
    before = [r for r in rows if r['t'] <= timeout_s]
    after = [r for r in rows if r['t'] >= end]
    if not before or not after:
        result['reason'] = 'OBSERVATION_WINDOW_INCOMPLETE'
        return result
    first, last = before[-1], after[0]
    selected = [r for r in rows if first['t'] <= r['t'] <= last['t']]
    gaps=[b['t']-a['t'] for a,b in zip(selected,selected[1:])]
    metrics.update(maximum_sample_gap_ms=max(gaps,default=0)*1000,
        leading_bracket_ms=(timeout_s-first['t'])*1000,trailing_bracket_ms=(last['t']-end)*1000)
    if (timeout_s-first['t'] > policy['max_sample_gap_s']
            or last['t']-end > policy['max_sample_gap_s']
            or any(gap > policy['max_sample_gap_s'] for gap in gaps)):
        result['reason'] = 'SENSOR_COVERAGE_INVALID'
        return result
    if any(not finite(r.get('source_age_s')) or not 0 <= r['source_age_s'] < POLICY['max_source_age_s']
           for r in selected):
        result['reason'] = 'SENSOR_SOURCE_AGE_INVALID'
        return result
    if any(r.get('torque') is not True for r in selected):
        result['reason'] = 'OBSERVATION_INTERRUPTED_BY_TORQUE_OFF'
        return result
    checks['continuous_torque_on_observation'] = True
    metrics['observed_ms'] = (last['t']-first['t'])*1000
    travel = [sum(abs(b['encoders'][i]-a['encoders'][i]) for a,b in zip(selected,selected[1:]))*MM_PER_TICK
              for i in range(2)]
    metrics['wheel_travel_mm'] = travel
    checks['wheel_travel_bounded'] = max(travel) <= POLICY['wheel_travel_limit_mm']
    verify_start = timeout_s + POLICY['deceleration_budget_s']
    bracket = [r for r in selected if r['t'] <= verify_start][-1]
    tail = [r for r in selected if r['t'] >= bracket['t']]
    spans = [(max(r['encoders'][i] for r in tail)-min(r['encoders'][i] for r in tail))*MM_PER_TICK
             for i in range(2)]
    # Range, not only endpoint delta: oscillation cannot cancel residual motion.
    # Fixed nominal denominator is conservative when bracketing adds samples.
    rates = [s/POLICY['verification_s'] for s in spans]
    metrics.update(residual_span_mm=spans, residual_rate_mm_s=rates,
                   verification_observed_ms=(last['t']-bracket['t'])*1000)
    checks['residual_motion_bounded'] = max(rates) <= POLICY['residual_rate_limit_mm_s']
    if not checks['wheel_travel_bounded']:
        result.update(status='FAIL', reason='STOP_TRAVEL_EXCEEDED')
    elif not checks['residual_motion_bounded']:
        result.update(status='FAIL', reason='RESIDUAL_MOTION_EXCEEDED')
    else:
        result.update(status='PASS', reason='SUPERVISED_STOP_METRICS_PASSED')
    return result
