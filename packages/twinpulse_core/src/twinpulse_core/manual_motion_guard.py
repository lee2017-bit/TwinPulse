# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure native-angle / directional-sweep / wheel-vs-body checks.

No transport, motor command, calibration defaults, resampling or live authority.
Evidence digests are provenance references, NOT proof that a measurement is
correct: a trusted integration must resolve them against reviewed measurements.
No calibration is shipped for the user's robot. Fixture and measured evidence
cannot be mixed. A result is conditional on an explicit 2D opaque-target sampling
model; glass, low/overhead objects and narrower targets remain outside that model.

Forward/reverse coverage is directional: only advancing footprint faces and
their expanded stopping sweep are checked. Unknown rays on the opposite side
do not veto that direction. Rotation uses a conservative full-rotation envelope.
Adjacent *original* rays bound free-space triangles under the measured sampling
model, never invented uniform rays. Required sectors with missing/poor returns
or excessive gaps are UNKNOWN, never free. Stopping is always permitted.
"""
from dataclasses import dataclass
import math
import re
from .robot_control_timing import INPUT_TTL_S

EPS = 1e-10
KINDS = {'synthetic_test_fixture', 'saved_sensor_recording', 'live_sensor'}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _number(value, low, high):
    return _finite(value) and low <= value <= high


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def _xy(value):
    return type(value) is tuple and len(value) == 2 and all(_number(v, -100, 100) for v in value)


def _cross(a, b, p):
    return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])


def _hull(points):
    values = sorted(set(points))
    halves = []
    for ordered in (values, list(reversed(values))):
        half = []
        for point in ordered:
            while len(half) >= 2 and _cross(half[-2], half[-1], point) <= EPS:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return tuple(halves[0]+halves[1])


def _inside(point, polygon):
    return all(_cross(a, b, point) >= -EPS for a, b in zip(polygon, polygon[1:]+polygon[:1]))


def _clip(polygon, a, b, sign=1):
    """Clip convex polygon to sign*cross(a,b,p)>=0; preserve measured vertices."""
    if not polygon:
        return ()
    result = []
    previous = polygon[-1]
    before = sign*_cross(a, b, previous)
    for point in polygon:
        after = sign*_cross(a, b, point)
        if (before >= 0) != (after >= 0):
            ratio = before/(before-after)
            result.append((previous[0]+ratio*(point[0]-previous[0]),
                           previous[1]+ratio*(point[1]-previous[1])))
        if after >= 0:
            result.append(point)
        previous, before = point, after
    return tuple(result)


def _arc(polygon, origin):
    if _inside(origin, polygon):
        return 0., math.tau
    angles = sorted(math.atan2(p[1]-origin[1], p[0]-origin[0]) % math.tau for p in polygon)
    gaps = [(angles[(i+1) % len(angles)]-a) % math.tau for i, a in enumerate(angles)]
    index = max(range(len(gaps)), key=gaps.__getitem__)
    return angles[(index+1) % len(angles)], math.tau-gaps[index]


def _overlap(start, width, other_start, other_width):
    return any(max(start, other_start+shift) <= min(start+width, other_start+shift+other_width)+EPS
               for shift in (-math.tau, 0., math.tau))


@dataclass(frozen=True)
class NativeBeam:
    angle_deg: float
    distance_m: float
    quality: int
    node_index: int
    source_byte_cursor: int


@dataclass(frozen=True)
class NativeFrame:
    beams: tuple
    sensor_frame: str
    source_kind: str
    raw_sha256: str
    nodes_sha256: str
    oldest_sample_s: float | None
    newest_sample_s: float | None
    timestamp_basis: str
    timing_evidence_sha256: str | None = None
    maximum_pipeline_age_s: float | None = None


@dataclass(frozen=True)
class NativeGeometry:
    # Pose of the sensor in base_link; handedness comes from measured axes.
    sensor_frame: str
    sensor_xy_yaw: tuple
    native_angle_sign: int
    footprint_xy_m: tuple  # Strictly convex, CCW, includes base origin.
    provenance: str  # measured or synthetic_test_fixture
    planar_extrinsic_sha256: str
    footprint_sha256: str


@dataclass(frozen=True)
class SamplingModel:
    minimum_range_m: float
    maximum_range_m: float
    minimum_quality: int
    maximum_gap_deg: float
    minimum_target_width_m: float
    range_uncertainty_m: float
    provenance: str
    opaque_target_coverage_sha256: str


@dataclass(frozen=True)
class NativePoint:
    beam: NativeBeam  # Original object/angle/order retained, including invalids.
    base_xy_m: tuple | None
    reason: str | None


@dataclass(frozen=True)
class AdaptedNativeFrame:
    source: NativeFrame
    geometry: NativeGeometry
    sampling: SamplingModel
    points: tuple


def _frame(frame):
    if (not isinstance(frame, NativeFrame) or frame.source_kind not in KINDS
            or not isinstance(frame.sensor_frame, str) or not frame.sensor_frame
            or not _hash(frame.raw_sha256) or not _hash(frame.nodes_sha256)
            or type(frame.beams) is not tuple or not 2 <= len(frame.beams) <= 4096):
        raise ValueError('NATIVE_FRAME_INVALID')
    previous = -1
    for beam in frame.beams:
        if (not isinstance(beam, NativeBeam) or not _number(beam.angle_deg, 0, 360)
                or not _number(beam.distance_m, 0, 65.535)
                or type(beam.quality) is not int or not 0 <= beam.quality <= 255
                or type(beam.node_index) is not int or beam.node_index <= previous
                or type(beam.source_byte_cursor) is not int or beam.source_byte_cursor < 0):
            raise ValueError('NATIVE_BEAM_INVALID')
        previous = beam.node_index


def audit_native_frame(frame):
    """Descriptive sensor-native audit; no TF, free-space or timing assertion."""
    _frame(frame)
    angles = sorted(b.angle_deg % 360 for b in frame.beams)
    gaps = [b-a for a, b in zip(angles, angles[1:])] + [angles[0]+360-angles[-1]]
    return {'samples': len(frame.beams), 'zero_returns': sum(b.distance_m == 0 for b in frame.beams),
            'minimum_gap_deg': min(gaps), 'maximum_gap_deg': max(gaps),
            'uniform_resampling': False, 'base_frame_verified': False, 'physical_authority': False}


def adapt_native_frame(frame, geometry, sampling):
    _frame(frame)
    expected = 'synthetic_test_fixture' if frame.source_kind == 'synthetic_test_fixture' else 'measured'
    if (not isinstance(geometry, NativeGeometry) or geometry.provenance != expected
            or geometry.sensor_frame != frame.sensor_frame
            or not _hash(geometry.planar_extrinsic_sha256) or not _hash(geometry.footprint_sha256)
            or type(geometry.sensor_xy_yaw) is not tuple or len(geometry.sensor_xy_yaw) != 3
            or not all(_number(v, -math.pi, math.pi) for v in geometry.sensor_xy_yaw)
            or type(geometry.native_angle_sign) is not int or geometry.native_angle_sign not in (-1, 1)
            or type(geometry.footprint_xy_m) is not tuple or not 3 <= len(geometry.footprint_xy_m) <= 16
            or not all(_xy(p) and math.hypot(*p) <= 2 for p in geometry.footprint_xy_m)):
        raise ValueError('MEASURED_PLANAR_EXTRINSIC_AND_FOOTPRINT_REQUIRED')
    polygon = geometry.footprint_xy_m
    start = polygon.index(min(polygon))
    if (any(_cross(polygon[i-1], polygon[i], polygon[(i+1) % len(polygon)]) <= EPS for i in range(len(polygon)))
            or _hull(polygon) != polygon[start:]+polygon[:start] or not _inside((0., 0.), polygon)):
        raise ValueError('FOOTPRINT_MUST_BE_CONVEX_CCW_AND_CONTAIN_BASE')
    if (not isinstance(sampling, SamplingModel) or sampling.provenance != expected
            or not _hash(sampling.opaque_target_coverage_sha256)
            or not _number(sampling.minimum_range_m, .000001, 65)
            or not _number(sampling.maximum_range_m, sampling.minimum_range_m, 65.535)
            or type(sampling.minimum_quality) is not int or not 0 <= sampling.minimum_quality <= 255
            or not _number(sampling.maximum_gap_deg, .000001, 45)
            or not _number(sampling.minimum_target_width_m, .000001, 1)
            or not _number(sampling.range_uncertainty_m, 0, 1)):
        raise ValueError('MEASURED_SAMPLING_MODEL_REQUIRED')
    tx, ty, yaw = geometry.sensor_xy_yaw
    points = []
    for beam in frame.beams:
        reason = ('NO_RETURN' if beam.distance_m == 0 else 'RANGE_OUTSIDE_MODEL'
                  if not sampling.minimum_range_m <= beam.distance_m <= sampling.maximum_range_m
                  else 'LOW_QUALITY' if beam.quality < sampling.minimum_quality else None)
        angle = yaw+geometry.native_angle_sign*math.radians(beam.angle_deg)
        point = None if reason else (tx+beam.distance_m*math.cos(angle), ty+beam.distance_m*math.sin(angle))
        points.append(NativePoint(beam, point, reason))
    return AdaptedNativeFrame(frame, geometry, sampling, tuple(points))


@dataclass(frozen=True)
class StopModel:
    body_clearance_m: float  # Must be at least 10 cm; never silently clamped.
    reaction_s: float
    minimum_linear_deceleration_m_s2: float
    minimum_angular_deceleration_rad_s2: float
    linear_velocity_uncertainty_m_s: float
    angular_velocity_uncertainty_rad_s: float
    position_uncertainty_m: float
    maximum_scan_age_s: float
    maximum_input_age_s: float
    maximum_linear_speed_m_s: float
    maximum_angular_speed_rad_s: float
    provenance: str
    stopping_measurement_sha256: str


@dataclass(frozen=True)
class MotionIntent:
    linear_m_s: float
    angular_rad_s: float
    created_s: float
    measured_linear_m_s: float | None
    measured_angular_rad_s: float | None
    measured_velocity_s: float | None


def _decision(reason, *, clear=False, **details):
    return dict(reason=reason, model_clear=clear, requires_stop=not clear,
                physical_authority=False, live_authority=False, **details)


def evaluate_manual_motion(intent, frame, geometry, sampling, stop_model, now):
    """Conditional model result, not a lease/arm command or hardware acceptance.

    Callers retain the original input/sample timestamps. This never restamps a
    command, fills missing returns, repairs calibration or resumes motion.
    """
    if (not isinstance(intent, MotionIntent) or not all(_finite(v) for v in
            (intent.linear_m_s, intent.angular_rad_s, intent.created_s, now))):
        return _decision('INTENT_INVALID')
    v, w = intent.linear_m_s, intent.angular_rad_s
    if v == 0 and w == 0:
        return _decision('STOP', clear=True)
    try:
        adapted = adapt_native_frame(frame, geometry, sampling)
    except ValueError as error:
        return _decision(str(error))
    expected = geometry.provenance
    policy = stop_model
    if (not isinstance(policy, StopModel) or policy.provenance != expected
            or not _hash(policy.stopping_measurement_sha256)
            or not _number(policy.body_clearance_m, .1, 2)
            or not _number(policy.reaction_s, 0, 5)
            or not _number(policy.minimum_linear_deceleration_m_s2, .000001, 100)
            or not _number(policy.minimum_angular_deceleration_rad_s2, .000001, 100)
            or not _number(policy.linear_velocity_uncertainty_m_s, 0, 1)
            or not _number(policy.angular_velocity_uncertainty_rad_s, 0, 2)
            or not _number(policy.position_uncertainty_m, 0, 1)
            or not _number(policy.maximum_scan_age_s, .000001, .2)
            or not _number(policy.maximum_input_age_s, .000001, INPUT_TTL_S)
            or not _number(policy.maximum_linear_speed_m_s, .000001, .05)
            or not _number(policy.maximum_angular_speed_rad_s, .000001, .3)):
        return _decision('MEASURED_STOP_MODEL_REQUIRED')
    if not 0 <= now-intent.created_s < policy.maximum_input_age_s:
        return _decision('INPUT_EXPIRED_OR_CLOCK_MISMATCH')
    interval_timing = (frame.timestamp_basis == 'conservative_measured_interval'
                       and _hash(frame.timing_evidence_sha256)
                       and _number(frame.maximum_pipeline_age_s, .000001, .2))
    if (not (frame.timestamp_basis == 'measured_beam_clock' or interval_timing) or not _finite(frame.oldest_sample_s)
            or not _finite(frame.newest_sample_s)
            or not frame.oldest_sample_s <= frame.newest_sample_s <= now
            or now-frame.oldest_sample_s >= policy.maximum_scan_age_s):
        return _decision('BEAM_TIMING_MISSING_OR_STALE')
    measured = (intent.measured_linear_m_s, intent.measured_angular_rad_s)
    if (not all(_finite(value) for value in measured) or not _finite(intent.measured_velocity_s)
            or not 0 <= now-intent.measured_velocity_s < policy.maximum_scan_age_s
            or max(abs(v), abs(measured[0])) > policy.maximum_linear_speed_m_s
            or max(abs(w), abs(measured[1])) > policy.maximum_angular_speed_rad_s):
        return _decision('VELOCITY_UNKNOWN_OR_OUTSIDE_MODEL')
    if v and w:
        return _decision('COMBINED_TRANSLATION_ROTATION_UNSUPPORTED')
    if (v and (v*measured[0] < 0 or abs(measured[1]) > policy.angular_velocity_uncertainty_rad_s)
            or w and (w*measured[1] < 0 or abs(measured[0]) > policy.linear_velocity_uncertainty_m_s)):
        return _decision('DIRECTION_CHANGE_REQUIRES_VERIFIED_STOP')
    footprint = geometry.footprint_xy_m
    origin = geometry.sensor_xy_yaw[:2]
    radius = max(math.hypot(*point) for point in footprint)
    margin = policy.body_clearance_m+policy.position_uncertainty_m+sampling.range_uncertainty_m
    speed = max(abs(v), abs(measured[0]))+policy.linear_velocity_uncertainty_m_s
    angular = max(abs(w), abs(measured[1]))+policy.angular_velocity_uncertainty_rad_s
    sample_age = now-frame.oldest_sample_s
    reaction = (speed*policy.reaction_s+policy.maximum_linear_speed_m_s*sample_age if v
                else radius*(angular*policy.reaction_s+policy.maximum_angular_speed_rad_s*sample_age))
    braking = (speed*speed/(2*policy.minimum_linear_deceleration_m_s2) if v
               else radius*angular*angular/(2*policy.minimum_angular_deceleration_rad_s2))
    # A small cross-axis reading is not silently rounded to zero. Only a
    # measured uncertainty envelope can admit it, and its residual displacement
    # enlarges the checked swept region (including side/rear coverage).
    cross_axis = bool(measured[1] if v else measured[0])
    if cross_axis:
        horizon = sample_age+policy.reaction_s+max(speed/policy.minimum_linear_deceleration_m_s2,
                                                  angular/policy.minimum_angular_deceleration_rad_s2)
        margin += (radius*(abs(measured[1])+policy.angular_velocity_uncertainty_rad_s) if v
                   else abs(measured[0])+policy.linear_velocity_uncertainty_m_s)*horizon
    # Circumscribed 32-gon contains, never underestimates, the requested disk.
    def disk(distance):
        distance /= math.cos(math.pi/32)
        return tuple((distance*math.cos(i*math.tau/32), distance*math.sin(i*math.tau/32)) for i in range(32))
    if v:
        shift = math.copysign(reaction+braking, v)
        sweep = _hull(tuple(footprint)+tuple((x+shift, y) for x, y in footprint))
        expanded = _hull(tuple((p[0]+d[0], p[1]+d[1]) for p in sweep for d in disk(margin)))
        # Only faces advancing into the commanded direction need coverage.
        regions = tuple(_clip(expanded, a, b, -1) for a, b in zip(footprint, footprint[1:]+footprint[:1])
                        if (b[1]-a[1])*math.copysign(1, v) > EPS)
        if cross_axis:regions=(expanded,)
    else:
        regions = (disk(radius+margin+reaction+braking),)
    details = dict(direction='forward' if v > 0 else 'reverse' if v < 0 else 'rotation',
        clearance_m=policy.body_clearance_m, reaction_distance_m=reaction, braking_distance_m=braking,
        uncertainty_margin_m=policy.position_uncertainty_m+sampling.range_uncertainty_m,
        checked_sectors=0, ignored_sectors=0, source_kind=frame.source_kind,
        measured_cross_axis_envelope=cross_axis,
        limits=['Conditional 2D opaque-target sampling model, not physical motion authority.',
                'Glass, low/overhead objects and targets narrower than the measured model remain unqualified.'])
    for point in adapted.points:
        if point.base_xy_m is not None and any(_inside(point.base_xy_m, region) for region in regions):
            return _decision('OBSTACLE_IN_DIRECTIONAL_SWEEP', node_index=point.beam.node_index, **details)
    required_arcs = [_arc(region, origin) for region in regions]
    needed_radius = max(math.dist(origin, point) for region in regions for point in region)
    ordered = sorted(adapted.points, key=lambda p: (geometry.sensor_xy_yaw[2]
        +geometry.native_angle_sign*math.radians(p.beam.angle_deg)) % math.tau)
    angles = [(geometry.sensor_xy_yaw[2]+geometry.native_angle_sign*math.radians(p.beam.angle_deg)) % math.tau for p in ordered]
    for a, b in zip(angles, angles[1:]):
        if b-a <= EPS and any(_overlap(a, 0., start, width) for start, width in required_arcs):
            return _decision('REQUIRED_DUPLICATE_ANGLE_AMBIGUOUS', **details)
    for index, first in enumerate(ordered):
        following = (index+1) % len(ordered)
        second = ordered[following]
        start, gap = angles[index], (angles[following]-angles[index]) % math.tau
        if gap <= EPS:
            continue
        if not any(_overlap(start, gap, arc_start, arc_width) for arc_start, arc_width in required_arcs):
            details['ignored_sectors'] += 1
            continue
        details['checked_sectors'] += 1
        if (first.reason or second.reason or math.degrees(gap) > sampling.maximum_gap_deg+EPS
                or 2*needed_radius*math.sin(gap/2) > sampling.minimum_target_width_m+EPS):
            return _decision('REQUIRED_DIRECTION_COVERAGE_UNKNOWN', **details)
        a, b = first.base_xy_m, second.base_xy_m
        for region in regions:
            needed = _clip(_clip(region, origin, a), origin, b, -1)
            # The ray triangle's far edge bounds sampled free space; a short
            # return never establishes freedom beyond itself, even if self-hit.
            if needed and any(_cross(a, b, point) <= EPS for point in needed):
                return _decision('REQUIRED_SWEEP_NOT_COVERED_BY_RETURNS', **details)
    if not details['checked_sectors']:
        return _decision('REQUIRED_DIRECTION_COVERAGE_UNKNOWN', **details)
    return _decision('CLEAR_UNDER_DECLARED_SAMPLING_MODEL', clear=True, **details)


@dataclass(frozen=True)
class ProgressThresholds:
    window_s: float
    maximum_sample_gap_s: float
    minimum_command_m_s: float
    minimum_wheel_progress_m: float
    minimum_body_translation_m: float | None
    minimum_body_rotation_rad: float | None
    maximum_wheel_speed_m_s: float
    maximum_body_speed_m_s: float | None
    maximum_body_rotation_rad_s: float | None
    provenance: str
    measurement_sha256: str


@dataclass(frozen=True)
class ProgressObservation:
    sample_s: float
    epoch: str
    wheel_distances_m: tuple
    wheel_error_m: float
    body_xy_yaw: tuple | None
    body_position_error_m: float
    body_yaw_error_rad: float
    body_source: str
    body_frame: str | None
    body_evidence_sha256: str | None
    body_tracking_epoch: str | None = None


class WheelBodyProgressMonitor:
    """Bounded measured-delta monitor, never derives body pose from encoders.

    Inputs are cumulative calibrated wheel distances and an independent body
    pose in a stable frame. Changing epoch, command direction or pose source
    resets the window. WARMUP is not failure and does not itself grant motion.
    Thresholds/uncertainties are explicit and must be measured for live use.
    The explicitly wheel-only branch may retain unknown body-only thresholds
    as None; this never creates body-motion evidence, even if a pose is present.
    """
    def __init__(self, thresholds, *, require_independent_body=True):
        p = thresholds
        if type(require_independent_body) is not bool:raise ValueError('BODY_PROGRESS_POLICY_INVALID')
        if (not isinstance(p, ProgressThresholds) or p.provenance not in {'measured', 'synthetic_test_fixture'}
                or not _hash(p.measurement_sha256) or not _number(p.window_s, .05, 5)
                or not _number(p.maximum_sample_gap_s, .001, p.window_s)
                or any(not _number(value, .000001, 10) for value in (
                    p.minimum_command_m_s, p.minimum_wheel_progress_m, p.maximum_wheel_speed_m_s))):
            raise ValueError('PROGRESS_MEASUREMENTS_REQUIRED')
        body_limits=(p.minimum_body_translation_m,p.minimum_body_rotation_rad,
                     p.maximum_body_speed_m_s,p.maximum_body_rotation_rad_s)
        if any(not _number(value,.000001,10) and not (value is None and not require_independent_body)
               for value in body_limits):raise ValueError('PROGRESS_MEASUREMENTS_REQUIRED')
        self.body_model_available=all(value is not None for value in body_limits)
        self.thresholds, self.samples, self.context, self.fault = p, [], None, None
        self.require_independent_body = require_independent_body

    def reset(self):
        """Explicit new monitoring generation; never grants arm/motion authority."""
        self.samples, self.context, self.fault = [], None, None

    def _result(self, reason, *, wheel='UNKNOWN', body='UNVERIFIED', stop=True, **details):
        result = dict(reason=reason, wheel_progress=wheel, body_progress=body,
                      requires_stop=stop, physical_authority=False, **details)
        if stop:
            self.fault = dict(result)
        return result

    def observe(self, observation, commanded_wheel_m_s, *, progress_kind, now):
        p, sample = self.thresholds, observation
        if (type(commanded_wheel_m_s) is not tuple or len(commanded_wheel_m_s) != 2
                or not all(_finite(v) for v in commanded_wheel_m_s) or not _finite(now)):
            self.samples.clear()
            return self._result('PROGRESS_COMMAND_INVALID')
        if commanded_wheel_m_s == (0, 0):
            self.samples.clear()
            self.context = None
            return self._result('IDLE', wheel='NOT_REQUESTED', body='NOT_REQUESTED', stop=False)
        if self.fault is not None:
            return dict(self.fault)
        if (progress_kind not in {'translation', 'rotation'}
                or any(not p.minimum_command_m_s <= abs(v) <= p.maximum_wheel_speed_m_s for v in commanded_wheel_m_s)
                or (commanded_wheel_m_s[0]*commanded_wheel_m_s[1] > 0) != (progress_kind == 'translation')):
            self.samples.clear()
            return self._result('PROGRESS_COMMAND_OUTSIDE_MODEL')
        if (not isinstance(sample, ProgressObservation) or not _finite(sample.sample_s)
                or not 0 <= now-sample.sample_s <= p.maximum_sample_gap_s
                or not isinstance(sample.epoch, str) or not sample.epoch
                or type(sample.wheel_distances_m) is not tuple or len(sample.wheel_distances_m) != 2
                or not all(_finite(v) for v in sample.wheel_distances_m)
                or not _number(sample.wheel_error_m, 0, 1)
                or not _number(sample.body_position_error_m, 0, 1)
                or not _number(sample.body_yaw_error_rad, 0, math.pi)):
            self.samples.clear()
            return self._result('PROGRESS_SAMPLE_INVALID_OR_STALE')
        context = (sample.epoch, progress_kind, tuple(math.copysign(1, v) for v in commanded_wheel_m_s),
                   sample.body_source, sample.body_frame, sample.body_tracking_epoch)
        if context != self.context:
            self.samples.clear()
            self.context = context
        if self.samples:
            previous = self.samples[-1]
            dt = sample.sample_s-previous.sample_s
            if not 0 < dt <= p.maximum_sample_gap_s:
                self.samples.clear()
                return self._result('PROGRESS_CLOCK_OR_SAMPLE_GAP')
            if any(abs(a-b) > p.maximum_wheel_speed_m_s*dt+sample.wheel_error_m+previous.wheel_error_m+EPS
                   for a, b in zip(sample.wheel_distances_m, previous.wheel_distances_m)):
                self.samples.clear()
                return self._result('WHEEL_RESET_OR_IMPLAUSIBLE_JUMP')
        self.samples.append(sample)
        if len(self.samples) > 1024:
            self.samples.clear()
            return self._result('PROGRESS_SAMPLE_CAPACITY')
        while len(self.samples) > 2 and self.samples[1].sample_s <= sample.sample_s-p.window_s:
            self.samples.pop(0)
        first = self.samples[0]
        if sample.sample_s-first.sample_s+EPS < p.window_s:
            return self._result('WARMUP', stop=False)
        wheel = tuple((end-start)*direction-first.wheel_error_m-sample.wheel_error_m
                      for start, end, direction in zip(first.wheel_distances_m, sample.wheel_distances_m, context[2]))
        details = dict(wheel_progress_lower_m=wheel, observed_window_s=sample.sample_s-first.sample_s)
        if any(delta < p.minimum_wheel_progress_m for delta in wheel):
            return self._result('WHEEL_STALL_OR_REVERSE_PROGRESS', wheel='STALLED', **details)
        if not self.body_model_available:
            return self._result('BODY_PROGRESS_MODEL_UNVERIFIED',wheel='MOVING',stop=False,**details)
        independent = {'independent_scan_match', 'external_tracking'}
        if (sample.body_source not in independent or not _hash(sample.body_evidence_sha256)
                or not isinstance(sample.body_frame, str) or not sample.body_frame
                or any(type(s.body_xy_yaw) is not tuple or len(s.body_xy_yaw) != 3
                       or not all(_finite(v) for v in s.body_xy_yaw) for s in self.samples)):
            return self._result('BODY_PROGRESS_UNVERIFIED', wheel='MOVING',
                                stop=self.require_independent_body, **details)
        for before, after in zip(self.samples, self.samples[1:]):
            dt = after.sample_s-before.sample_s
            translation = math.dist(before.body_xy_yaw[:2], after.body_xy_yaw[:2])
            rotation = abs(math.remainder(after.body_xy_yaw[2]-before.body_xy_yaw[2], math.tau))
            if (translation > p.maximum_body_speed_m_s*dt+before.body_position_error_m+after.body_position_error_m+EPS
                    or rotation > p.maximum_body_rotation_rad_s*dt+before.body_yaw_error_rad+after.body_yaw_error_rad+EPS):
                self.samples.clear()
                return self._result('BODY_POSE_JUMP_UNVERIFIED', wheel='MOVING', **details)
        translation = math.dist(first.body_xy_yaw[:2], sample.body_xy_yaw[:2])-first.body_position_error_m-sample.body_position_error_m
        dx, dy = sample.body_xy_yaw[0]-first.body_xy_yaw[0], sample.body_xy_yaw[1]-first.body_xy_yaw[1]
        projected = ((dx*math.cos(first.body_xy_yaw[2])+dy*math.sin(first.body_xy_yaw[2]))*context[2][0]
                     -first.body_position_error_m-sample.body_position_error_m)
        rotation = (math.remainder(sample.body_xy_yaw[2]-first.body_xy_yaw[2], math.tau)
                    *math.copysign(1, commanded_wheel_m_s[1]-commanded_wheel_m_s[0])
                    -first.body_yaw_error_rad-sample.body_yaw_error_rad)
        details.update(body_translation_lower_m=translation, body_requested_translation_lower_m=projected,
                       body_rotation_lower_rad=rotation)
        progress = projected if progress_kind == 'translation' else rotation
        threshold = p.minimum_body_translation_m if progress_kind == 'translation' else p.minimum_body_rotation_rad
        if progress < threshold:
            error=(first.body_position_error_m+sample.body_position_error_m if progress_kind=='translation'
                   else first.body_yaw_error_rad+sample.body_yaw_error_rad)
            if progress+2*error < threshold:
                return self._result('WHEELS_MOVING_BODY_STALLED', wheel='MOVING', body='STALLED', **details)
            return self._result('BODY_PROGRESS_INCONCLUSIVE', wheel='MOVING', body='INCONCLUSIVE', **details)
        return self._result('WHEEL_AND_INDEPENDENT_BODY_PROGRESS', wheel='MOVING', body='MOVING', stop=False, **details)
