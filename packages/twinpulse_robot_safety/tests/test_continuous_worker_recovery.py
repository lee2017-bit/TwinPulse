# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exact control() loop regressions; fake clock/link only, no ROS/SSH/devices."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'twinpulse_core/src'))
from control_timing import INPUT_TTL_S, INPUT_TTL_MS
from teleop_contract import InputGate
from teleop_worker import control


class Clock:
    def __init__(self):
        self.now = 1.

    def __call__(self):
        return self.now


class Link:
    def __init__(self, clock):
        self.clock, self.enabled, self.reason = clock, False, None
        self.sensor = SimpleNamespace(battery=12.)
        self.sensor_connected = True
        self.actions, self.published = [], []
        self.release_error = None

    def enable(self):
        self.enabled = True
        self.actions.append('enable')
        self.clock.now += .11

    def release(self):
        self.actions.append('release')
        if self.release_error:
            raise ValueError(self.release_error)
        self.enabled = False
        self.clock.now += .02

    def halt(self):
        self.actions.append('halt')
        self.enabled = False

    def publish(self, v, w, age):
        self.published.append((v, w, age))

    def spin(self, seconds):
        self.clock.now += seconds
        if self.clock.now > 3.:
            raise AssertionError('Worker did not complete scripted recovery')

    def fresh(self):
        assert self.sensor_connected


class ContinuousWorkerRecoveryTests(unittest.TestCase):
    def exercise_recovery(self, fault, *, mode='control'):
        clock = Clock()
        gate = InputGate(clock, continuous=True, persistent=True, recoverable=True)
        link = Link(clock)
        pre_arm = gate.challenge()
        emitted, events, stale_packets, checkpoints = [], [], [], []
        testcase = self

        class Incoming:
            step = 0

            def receive(self):
                last = emitted[-1]['challenge'] if emitted else None
                if self.step == 0:
                    self.step += 1
                    return dict(sequence=1, action='forward', challenge=last, age_ms=0.)
                if self.step == 1:
                    testcase.assertTrue(link.enabled)
                    testcase.assertFalse(gate.active)
                    testcase.assertFalse(gate.closed)
                    if fault == 'INPUT_EXPIRED':
                        # A genuinely expired, robot-issued post-arm nonce:
                        # retain its original timestamp and do not restamp it.
                        clock.now += INPUT_TTL_S+.001
                        nonce = last
                    else:
                        nonce = pre_arm
                    packet = dict(sequence=999, action='forward', challenge=nonce, age_ms=0.)
                    stale_packets.append(deepcopy(packet))
                    checkpoints.append((gate.sequence, gate.generation, gate.source_created))
                    self.step += 1
                    return packet
                if self.step == 2:
                    testcase.assertEqual(gate.sequence, 1)  # Rejected 999 never committed.
                    testcase.assertFalse(gate.active)
                    testcase.assertFalse(gate.closed)
                    testcase.assertFalse(link.enabled)
                    testcase.assertTrue(link.sensor_connected)
                    testcase.assertIsNone(gate.source_created)
                    testcase.assertEqual(gate.pause_reason, fault)
                    testcase.assertEqual(link.published, [])
                    testcase.assertNotIn('halt', link.actions)
                    testcase.assertEqual(link.actions, ['enable', 'release'])
                    self.step += 1
                    return dict(sequence=2, action='watch', challenge=last, age_ms=0.)
                if self.step == 3:
                    testcase.assertEqual(link.published, [])  # Watch does not resume.
                    testcase.assertFalse(link.enabled)
                    if last not in gate.challenges:
                        return None
                    self.step += 1
                    return dict(sequence=3, action='forward', challenge=last, age_ms=0.)
                if self.step == 4:
                    if last not in gate.challenges:
                        return None
                    testcase.assertTrue(link.enabled)
                    testcase.assertFalse(gate.active)
                    testcase.assertEqual(link.published, [])  # Arm input consumed.
                    self.step += 1
                    return dict(sequence=4, action='forward', challenge=last, age_ms=0.)
                if self.step == 5:
                    testcase.assertEqual(len(link.published), 1)
                    testcase.assertTrue(link.sensor_connected)
                    self.step += 1
                    return dict(sequence=5, action='close', challenge=None, age_ms=0.)
                raise AssertionError('Unexpected receive after explicit close')

        def record(kind, **data):
            if kind == 'motion_paused' and data['reason'] == fault:
                self.assertFalse(link.enabled)  # Stop before recording.
                self.assertEqual(link.actions[-1], 'release')
            events.append((kind, deepcopy(data)))

        result = control(link, Incoming(), lambda row: emitted.append(deepcopy(row)), mode,
                         gate=gate, clock=clock, record=record)
        self.assertEqual(result, {'status': 'OPERATOR_STOP'})
        self.assertEqual(link.actions, ['enable', 'release', 'enable', 'halt'])
        self.assertEqual([row['sequence'] for kind, row in events if kind == 'published'], [4])
        self.assertNotIn(999, [row['sequence'] for kind, row in events if kind == 'accepted'])
        self.assertTrue(any(row.get('pause_reason') == fault for row in emitted))
        self.assertGreater(next(row['motion_generation'] for kind, row in events if kind == 'motion_paused'), checkpoints[0][1])
        self.assertEqual(stale_packets[0]['age_ms'], 0.)
        if fault == 'INPUT_CHALLENGE':
            self.assertEqual(stale_packets[0]['challenge'], pre_arm)
        self.assertGreaterEqual(link.published[0][2], 0.)
        self.assertLess(link.published[0][2], INPUT_TTL_S)

    def test_late_pre_arm_challenge_pauses_without_worker_or_sensor_close(self):
        for mode in ('control', 'control_scan'):
            with self.subTest(mode=mode):
                self.exercise_recovery('INPUT_CHALLENGE', mode=mode)

    def test_expired_post_arm_input_pauses_and_only_fresh_input_can_resume(self):
        for mode in ('control', 'control_scan'):
            with self.subTest(mode=mode):
                self.exercise_recovery('INPUT_EXPIRED', mode=mode)

    def rejected_loop(self, *, persistent=True, recoverable=True, active=False, fault='INPUT_CHALLENGE', release_error=None):
        clock = Clock()
        gate = InputGate(clock, continuous=persistent, persistent=persistent, recoverable=recoverable)
        link = Link(clock)
        link.enabled = True
        link.release_error = release_error
        if active:
            gate.accept(dict(sequence=1, action='forward', challenge=gate.challenge(), age_ms=0.))
        packet = dict(sequence=2, action='forward', challenge='never-issued', age_ms=0.)
        if fault == 'INPUT_AGE':
            packet.update(challenge=gate.challenge(), age_ms=INPUT_TTL_MS)
        elif fault == 'INPUT_SEQUENCE':
            packet.update(sequence=0)
        incoming = SimpleNamespace(receive=lambda: packet)
        control(link, incoming, lambda _: None, 'control' if persistent else 'qualify', gate=gate, clock=clock)

    def test_in_motion_invalid_challenge_is_not_made_fail_open(self):
        with self.assertRaisesRegex(ValueError, '^INPUT_CHALLENGE$'):
            self.rejected_loop(active=True)

    def test_legacy_and_nonrecoverable_manual_behavior_unchanged(self):
        for values in ({'persistent': False, 'recoverable': False}, {'recoverable': False}):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, '^INPUT_CHALLENGE$'):
                self.rejected_loop(**values)

    def test_invalid_sequence_or_age_not_treated_as_transient_arm_input(self):
        for fault in ('INPUT_AGE', 'INPUT_SEQUENCE'):
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, '^'+fault+'$'):
                self.rejected_loop(fault=fault)

    def test_release_confirmation_fault_still_propagates(self):
        with self.assertRaisesRegex(ValueError, '^RELEASE_NOT_CONFIRMED$'):
            self.rejected_loop(release_error='RELEASE_NOT_CONFIRMED')


if __name__ == '__main__':
    unittest.main()
