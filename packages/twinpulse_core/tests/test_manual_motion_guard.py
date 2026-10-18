# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Synthetic fault/model checks and separately labelled saved-native audits."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core.manual_motion_guard import (
    NativeBeam, NativeFrame, NativeGeometry, SamplingModel, StopModel, MotionIntent,
    adapt_native_frame, audit_native_frame, evaluate_manual_motion,
    ProgressThresholds, ProgressObservation, WheelBodyProgressMonitor)

FIXTURE = 'synthetic_test_fixture'
SHA = 'a'*64


def fixture():
    # Alternating .8/1.2 degree spacing; not a uniform LaserScan fixture.
    beams = tuple(NativeBeam(i+(.2 if i % 2 else 0), 2., 200, i, 10+i*3) for i in range(360))
    frame = NativeFrame(beams, 'measured_sensor', FIXTURE, SHA, SHA, .95, .99, 'measured_beam_clock')
    geometry = NativeGeometry('measured_sensor', (.02, 0., 0.), 1,
        ((-.18, -.12), (.18, -.12), (.18, .12), (-.18, .12)), FIXTURE, SHA, SHA)
    sampling = SamplingModel(.02, 5., 100, 3., .05, .005, FIXTURE, SHA)
    stop = StopModel(.1, .25, .2, .5, .001, .01, .01, .2, .25, .05, .3, FIXTURE, SHA)
    intent = MotionIntent(.03, 0., .9, 0., 0., .99)
    return frame, geometry, sampling, stop, intent


class NativeDirectionalGuardTests(unittest.TestCase):
    def setUp(self):
        self.frame, self.geometry, self.sampling, self.stop, self.intent = fixture()

    def evaluate(self, **kwargs):
        values = dict(intent=self.intent, frame=self.frame, geometry=self.geometry,
                      sampling=self.sampling, stop_model=self.stop, now=1.)
        values.update(kwargs)
        return evaluate_manual_motion(**values)

    def beams(self, predicate, **changes):
        return replace(self.frame, beams=tuple(replace(b, **changes) if predicate(b) else b for b in self.frame.beams))

    def test_preserve_every_original_nonuniform_angle_order_and_metadata(self):
        value = adapt_native_frame(self.frame, self.geometry, self.sampling)
        self.assertEqual(tuple(p.beam for p in value.points), self.frame.beams)
        for point, beam in zip(value.points, self.frame.beams):
            self.assertIs(point.beam, beam)
            self.assertAlmostEqual(point.base_xy_m[0], .02+2*math.cos(math.radians(beam.angle_deg)))
            self.assertAlmostEqual(point.base_xy_m[1], 2*math.sin(math.radians(beam.angle_deg)))
        audit = audit_native_frame(self.frame)
        self.assertAlmostEqual(audit['minimum_gap_deg'], .8)
        self.assertAlmostEqual(audit['maximum_gap_deg'], 1.2)
        self.assertFalse(audit['uniform_resampling'])

    def test_measured_handedness_and_extrinsic_applied_without_angle_rewrite(self):
        geometry = replace(self.geometry, sensor_xy_yaw=(.02, -.01, math.pi/2), native_angle_sign=-1)
        points = adapt_native_frame(self.frame, geometry, self.sampling).points
        self.assertEqual(points[90].beam.angle_deg, 90.)
        self.assertAlmostEqual(points[90].base_xy_m[0], 2.02)
        self.assertAlmostEqual(points[90].base_xy_m[1], -.01)

    def test_unknown_returns_retained_as_unknown_not_dropped_or_infinity(self):
        frame = self.beams(lambda b: b.node_index == 0, distance_m=0.)
        points = adapt_native_frame(frame, self.geometry, self.sampling).points
        self.assertEqual(len(points), 360)
        self.assertIsNone(points[0].base_xy_m)
        self.assertEqual(points[0].reason, 'NO_RETURN')
        self.assertFalse(self.evaluate(frame=frame)['model_clear'])

    def test_missing_or_mixed_calibration_never_creates_base_points(self):
        for geometry in (None, replace(self.geometry, planar_extrinsic_sha256=''),
                         replace(self.geometry, provenance='measured'),
                         replace(self.geometry, sensor_frame='other')):
            with self.assertRaisesRegex(ValueError, 'EXTRINSIC_AND_FOOTPRINT'):
                adapt_native_frame(self.frame, geometry, self.sampling)
        with self.assertRaisesRegex(ValueError, 'SAMPLING_MODEL'):
            adapt_native_frame(self.frame, self.geometry, None)

    def test_malformed_nonconvex_cw_star_or_off_origin_footprint_rejected(self):
        polygons = [tuple(reversed(self.geometry.footprint_xy_m)),
                    ((0., 0.), (.2, 0.), (.1, .05), (.2, .2), (0., .2)),
                    ((1., 1.), (1.1, 1.), (1.1, 1.1), (1., 1.1))]
        ring = tuple((.2*math.cos(i*math.tau/5), .2*math.sin(i*math.tau/5)) for i in range(5))
        polygons.append(tuple(ring[i] for i in (0, 2, 4, 1, 3)))
        for polygon in polygons:
            with self.assertRaises(ValueError):
                adapt_native_frame(self.frame, replace(self.geometry, footprint_xy_m=polygon), self.sampling)

    def test_clear_under_explicit_model_is_never_live_authority(self):
        value = self.evaluate()
        self.assertTrue(value['model_clear'], value)
        self.assertFalse(value['physical_authority'])
        self.assertFalse(value['live_authority'])
        self.assertGreater(value['checked_sectors'], 0)
        self.assertGreater(value['ignored_sectors'], 0)
        self.assertAlmostEqual(value['clearance_m'], .1)
        self.assertAlmostEqual(value['reaction_distance_m'], .031*.25+.05*.05)
        self.assertAlmostEqual(value['braking_distance_m'], .031**2/.4)
        self.assertAlmostEqual(value['uncertainty_margin_m'], .015)

    def test_backward_unknown_does_not_block_forward_but_blocks_reverse(self):
        frame = self.beams(lambda b: 130 <= b.angle_deg <= 230, distance_m=0.)
        self.assertTrue(self.evaluate(frame=frame)['model_clear'])
        reverse = replace(self.intent, linear_m_s=-.03)
        value = self.evaluate(frame=frame, intent=reverse)
        self.assertEqual(value['reason'], 'REQUIRED_DIRECTION_COVERAGE_UNKNOWN')

    def test_forward_unknown_does_not_block_reverse_but_blocks_forward(self):
        frame = self.beams(lambda b: b.angle_deg < 50 or b.angle_deg > 310, quality=1)
        self.assertTrue(self.evaluate(frame=frame, intent=replace(self.intent, linear_m_s=-.03))['model_clear'])
        self.assertEqual(self.evaluate(frame=frame)['reason'], 'REQUIRED_DIRECTION_COVERAGE_UNKNOWN')

    def test_directional_near_obstacle_and_side_corner_are_blocked(self):
        frame = self.beams(lambda b: b.node_index == 0, distance_m=.23)
        self.assertEqual(self.evaluate(frame=frame)['reason'], 'OBSTACLE_IN_DIRECTIONAL_SWEEP')
        self.assertTrue(self.evaluate(frame=frame, intent=replace(self.intent, linear_m_s=-.03))['model_clear'])
        # Corner is outside physical y extent but inside the required margin.
        frame = self.beams(lambda b: b.node_index == 40, distance_m=.30)
        self.assertEqual(self.evaluate(frame=frame)['reason'], 'OBSTACLE_IN_DIRECTIONAL_SWEEP')

    def test_short_self_return_cannot_prove_space_beyond_front_edge(self):
        frame = self.beams(lambda b: b.node_index == 0, distance_m=.06)
        self.assertEqual(self.evaluate(frame=frame)['reason'], 'REQUIRED_SWEEP_NOT_COVERED_BY_RETURNS')

    def test_large_required_gap_rejected_but_opposite_gap_ignored(self):
        front = replace(self.frame, beams=tuple(b for b in self.frame.beams if not 10 < b.angle_deg < 25))
        rear = replace(self.frame, beams=tuple(b for b in self.frame.beams if not 150 < b.angle_deg < 210))
        self.assertEqual(self.evaluate(frame=front)['reason'], 'REQUIRED_DIRECTION_COVERAGE_UNKNOWN')
        self.assertTrue(self.evaluate(frame=rear)['model_clear'])

    def test_required_duplicate_angle_is_not_silently_averaged(self):
        beams = list(self.frame.beams)
        beams[1] = replace(beams[1], angle_deg=0.)
        self.assertEqual(self.evaluate(frame=replace(self.frame, beams=tuple(beams)))['reason'],
                         'REQUIRED_DUPLICATE_ANGLE_AMBIGUOUS')

    def test_rotation_requires_rear_coverage_and_uses_outer_body(self):
        intent = replace(self.intent, linear_m_s=0., angular_rad_s=.2)
        self.assertTrue(self.evaluate(intent=intent)['model_clear'])
        rear = self.beams(lambda b: 150 < b.angle_deg < 210, distance_m=0.)
        self.assertFalse(self.evaluate(intent=intent, frame=rear)['model_clear'])
        corner = self.beams(lambda b: b.node_index == 150, distance_m=.3)
        self.assertEqual(self.evaluate(intent=intent, frame=corner)['reason'], 'OBSTACLE_IN_DIRECTIONAL_SWEEP')

    def test_measurements_and_freshness_are_mandatory_no_restamping(self):
        for frame in (replace(self.frame, oldest_sample_s=None), replace(self.frame, oldest_sample_s=.5),
                      replace(self.frame, timestamp_basis='host_observation_window_not_beam_time')):
            self.assertEqual(self.evaluate(frame=frame)['reason'], 'BEAM_TIMING_MISSING_OR_STALE')
        for intent in (replace(self.intent, created_s=.75), replace(self.intent, created_s=1.1)):
            self.assertEqual(self.evaluate(intent=intent)['reason'], 'INPUT_EXPIRED_OR_CLOCK_MISMATCH')
        for intent in (replace(self.intent, measured_linear_m_s=None), replace(self.intent, measured_velocity_s=.5)):
            self.assertEqual(self.evaluate(intent=intent)['reason'], 'VELOCITY_UNKNOWN_OR_OUTSIDE_MODEL')
        self.assertEqual(self.frame.oldest_sample_s, .95)
        self.assertEqual(self.intent.created_s, .9)

    def test_no_relaxation_of_10cm_250ms_200ms_or_declared_stop_model(self):
        for policy in (None, replace(self.stop, body_clearance_m=.099), replace(self.stop, maximum_input_age_s=.5),
                       replace(self.stop, maximum_scan_age_s=.3), replace(self.stop, minimum_linear_deceleration_m_s2=0),
                       replace(self.stop, stopping_measurement_sha256='')):
            self.assertEqual(self.evaluate(stop_model=policy)['reason'], 'MEASURED_STOP_MODEL_REQUIRED')

    def test_stop_always_permitted_and_reversal_or_curved_motion_not_assumed(self):
        self.assertEqual(self.evaluate(intent=replace(self.intent, linear_m_s=0), frame=None, geometry=None,
                                       sampling=None, stop_model=None)['reason'], 'STOP')
        self.assertEqual(self.evaluate(intent=replace(self.intent, measured_linear_m_s=-.01))['reason'],
                         'DIRECTION_CHANGE_REQUIRES_VERIFIED_STOP')
        self.assertEqual(self.evaluate(intent=replace(self.intent, angular_rad_s=.1))['reason'],
                         'COMBINED_TRANSLATION_ROTATION_UNSUPPORTED')

    def test_more_uncertainty_or_slower_braking_never_turns_blocked_to_clear(self):
        for angle in (0, 15, 35, 50, 180):
            for distance in (.22, .28, .32, .40):
                frame = self.beams(lambda b: b.node_index == angle, distance_m=distance)
                baseline = self.evaluate(frame=frame)
                larger = self.evaluate(frame=frame, stop_model=replace(self.stop, position_uncertainty_m=.04,
                    reaction_s=.5, minimum_linear_deceleration_m_s2=.1))
                if not baseline['model_clear']:
                    self.assertFalse(larger['model_clear'])


def thresholds():
    return ProgressThresholds(.5, .15, .005, .002, .003, .01, .1, .1, .5, FIXTURE, SHA)


class WheelBodyProgressTests(unittest.TestCase):
    def test_supervised_null_body_model_remains_unverified_and_wheel_stall_still_stops(self):
        body=('minimum_body_translation_m','minimum_body_rotation_rad','maximum_body_speed_m_s','maximum_body_rotation_rad_s')
        model=replace(thresholds(),**{key:None for key in body})
        for independent,wheel_moves in ((False,True),(True,True),(False,False)):
            monitor=WheelBodyProgressMonitor(model,require_independent_body=False)
            for i in range(6):
                t=i*.1;distance=.03*t if wheel_moves else 0.
                sample=ProgressObservation(t,'epoch',(distance,distance),0.,(.03*t,0.,0.) if independent else None,
                    0.,0.,'external_tracking' if independent else 'wheel_encoder_only','map' if independent else None,SHA if independent else None)
                result=monitor.observe(sample,(.03,.03),progress_kind='translation',now=t)
            self.assertEqual(result['body_progress'],'UNVERIFIED')
            self.assertEqual(result['requires_stop'],not wheel_moves)
            self.assertEqual(result['reason'],'BODY_PROGRESS_MODEL_UNVERIFIED' if wheel_moves else 'WHEEL_STALL_OR_REVERSE_PROGRESS')
        for key in body:
            with self.assertRaisesRegex(ValueError,'PROGRESS_MEASUREMENTS_REQUIRED'):
                WheelBodyProgressMonitor(replace(thresholds(),**{key:None}),require_independent_body=True)
            for bad in (0,-1,float('nan'),float('inf'),True):
                with self.assertRaisesRegex(ValueError,'PROGRESS_MEASUREMENTS_REQUIRED'):
                    WheelBodyProgressMonitor(replace(model,**{key:bad}),require_independent_body=False)

    def run_window(self, *, wheels=True, body=True, source='independent_scan_match', rotate=False, reverse=False):
        monitor = WheelBodyProgressMonitor(thresholds())
        sign = -1 if reverse else 1
        command = (-.03, .03) if rotate else (sign*.03, sign*.03)
        for i in range(6):
            t = i*.1
            distances = tuple(v*t if wheels else 0. for v in command)
            pose = (0., 0., .1*t if body else 0.) if rotate else (sign*.03*t if body else 0., 0., 0.)
            sample = ProgressObservation(t, 'epoch-1', distances, 0., pose, 0., 0., source, 'map', SHA)
            result = monitor.observe(sample, command, progress_kind='rotation' if rotate else 'translation', now=t)
        return monitor, result, sample, command

    def test_wheel_stall_distinct_from_body_stall(self):
        self.assertEqual(self.run_window(wheels=False)[1]['reason'], 'WHEEL_STALL_OR_REVERSE_PROGRESS')
        value = self.run_window(body=False)[1]
        self.assertEqual(value['reason'], 'WHEELS_MOVING_BODY_STALLED')
        self.assertEqual((value['wheel_progress'], value['body_progress']), ('MOVING', 'STALLED'))

    def test_wheel_odom_never_proves_body_progress(self):
        value = self.run_window(source='wheel_odometry')[1]
        self.assertEqual(value['reason'], 'BODY_PROGRESS_UNVERIFIED')
        self.assertTrue(value['requires_stop'])

    def test_independent_translation_reverse_and_rotation_progress(self):
        for arguments in ({}, {'reverse': True}, {'rotate': True}):
            value = self.run_window(**arguments)[1]
            self.assertEqual(value['reason'], 'WHEEL_AND_INDEPENDENT_BODY_PROGRESS')
            self.assertFalse(value['physical_authority'])

    def test_fault_latches_until_explicit_reset_not_one_good_sample(self):
        monitor, value, sample, command = self.run_window(body=False)
        self.assertEqual(monitor.observe(replace(sample, sample_s=.6), command, progress_kind='translation', now=.6), value)
        monitor.observe(sample, (0, 0), progress_kind='translation', now=.5)
        self.assertEqual(monitor.observe(sample, command, progress_kind='translation', now=.5), value)
        monitor.reset()
        self.assertEqual(monitor.observe(sample, command, progress_kind='translation', now=.5)['reason'], 'WARMUP')

    def test_epoch_or_direction_reset_does_not_compare_disjoint_windows(self):
        monitor, _, sample, command = self.run_window()
        changed = replace(sample, epoch='epoch-2', sample_s=.6)
        self.assertEqual(monitor.observe(changed, command, progress_kind='translation', now=.6)['reason'], 'WARMUP')
        self.assertEqual(monitor.observe(replace(changed, sample_s=.7), (-.03, -.03), progress_kind='translation', now=.7)['reason'], 'WARMUP')

    def test_clock_gap_encoder_jump_and_pose_jump_are_not_motion_proof(self):
        monitor, _, sample, command = self.run_window()
        self.assertEqual(monitor.observe(sample, command, progress_kind='translation', now=.5)['reason'], 'PROGRESS_CLOCK_OR_SAMPLE_GAP')
        monitor.reset()
        monitor.observe(sample, command, progress_kind='translation', now=.5)
        jump = replace(sample, sample_s=.6, wheel_distances_m=(1., 1.))
        self.assertEqual(monitor.observe(jump, command, progress_kind='translation', now=.6)['reason'], 'WHEEL_RESET_OR_IMPLAUSIBLE_JUMP')
        monitor, _, sample, command = self.run_window()
        jump = replace(sample, sample_s=.6, wheel_distances_m=(.018, .018), body_xy_yaw=(3., 0., 0.))
        self.assertEqual(monitor.observe(jump, command, progress_kind='translation', now=.6)['reason'], 'BODY_POSE_JUMP_UNVERIFIED')

    def test_body_uncertainty_and_wrong_direction_cannot_pass(self):
        for direction, uncertainty in ((-1, 0.), (1, .02)):
            monitor = WheelBodyProgressMonitor(thresholds())
            for i in range(6):
                t = i*.1
                sample = ProgressObservation(t, 'epoch', (.03*t, .03*t), 0., (direction*.03*t, 0., 0.),
                                             uncertainty, 0., 'external_tracking', 'map', SHA)
                result = monitor.observe(sample, (.03, .03), progress_kind='translation', now=t)
            self.assertEqual(result['reason'], 'WHEELS_MOVING_BODY_STALLED' if direction<0 else 'BODY_PROGRESS_INCONCLUSIVE')
            self.assertTrue(result['requires_stop'])

    def test_changing_observation_hash_does_not_reset_stable_tracking_epoch(self):
        monitor=WheelBodyProgressMonitor(thresholds())
        for i in range(6):
            t=i*.1
            sample=ProgressObservation(t,'epoch',(.03*t,.03*t),0.,(.03*t,0.,0.),0.,0.,
                'external_tracking','map',hashlib.sha256(str(i).encode()).hexdigest(),'tracker-1')
            result=monitor.observe(sample,(.03,.03),progress_kind='translation',now=t)
        self.assertEqual(result['reason'],'WHEEL_AND_INDEPENDENT_BODY_PROGRESS')
        changed=replace(sample,sample_s=.6,body_tracking_epoch='tracker-2')
        self.assertEqual(monitor.observe(changed,(.03,.03),progress_kind='translation',now=.6)['reason'],'WARMUP')


class SavedNativeDataAuditTests(unittest.TestCase):
    def test_saved_corpus_preserved_and_blocked_without_actual_calibration(self):
        # Actual decoded sensor recordings, NOT synthetic geometry acceptance.
        manifest_path = ROOT / 'outputs/robot-fleet-20261017/decoder-verification.json'
        if not manifest_path.exists():
            self.skipTest('Saved robot corpus is not bundled with this checkout')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        results = []
        for recording in manifest['recordings']:
            path = manifest_path.parent / 'decoder-results-03' / (recording['name']+'-nodes.ndjson')
            payload = path.read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), recording['candidate_nodes_sha256'])
            current, frames, count, gaps = None, 0, 0, []
            for index, line in enumerate(payload.splitlines()):
                row = json.loads(line)
                beam = NativeBeam(row['angle_deg'], row['distance_m'], row['quality'], index, row['source_byte_cursor'])
                count += 1
                if row['ring_start']:
                    if current:
                        frame = NativeFrame(tuple(current), 'native_axes_unqualified', 'saved_sensor_recording',
                            recording['raw_sha256'], recording['candidate_nodes_sha256'], None, None,
                            'host_observation_window_not_beam_time')
                        audit = audit_native_frame(frame)
                        gaps.append((audit['minimum_gap_deg'], audit['maximum_gap_deg']))
                        with self.assertRaisesRegex(ValueError, 'EXTRINSIC_AND_FOOTPRINT'):
                            adapt_native_frame(frame, None, None)
                        frames += 1
                    current = []
                if current is not None:
                    current.append(beam)
            self.assertEqual(count, recording['decoded_samples'])
            self.assertGreater(frames, 0)
            self.assertTrue(any(high-low > .1 for low, high in gaps))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), recording['candidate_nodes_sha256'])
            results.append({'recording': recording['name'], 'nodes': count, 'complete_frames': frames,
                            'base_frame_adapter': 'BLOCKED_ACTUAL_CALIBRATION_MISSING',
                            'timing': 'HOST_WINDOW_NOT_BEAM_TIME', 'hardware': 'NOT_RUN'})
        print('SAVED_NATIVE_AUDIT '+json.dumps(results, separators=(',', ':')))


if __name__ == '__main__':
    unittest.main()
