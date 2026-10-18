# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device checks for the combined ROS evidence gate."""
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'packages/twinpulse_robot_safety'),
                str(ROOT / 'packages/twinpulse_core/src')]
from raw_ros_record import RawRosRecorder
from inspect_same_window_ros import inspect
from isolated_ros_scan import IsolatedRosScan
import isolated_ros_scan
from teleop_worker import wait_for_same_window_inputs
from teleop_contract import InputGate
import teleop_ros
from prepare_robot import bundle


class SameWindowTests(unittest.TestCase):
    def test_sensor_warmup_expires_qualify_lease_and_needs_new_watch(self):
        now = [1.]
        clock = lambda: now[0]
        gate = InputGate(clock)
        initial = gate.challenge()
        gate.accept({'sequence': 1, 'action': 'qualify', 'challenge': initial, 'age_ms': 0})
        gate.suspend_for_sensor_warmup()
        now[0] += 1.
        gate.check()  # No torque is enabled during a slow driver startup.
        self.assertFalse(gate.active)
        self.assertEqual(gate.challenges, {})
        fresh = gate.challenge()
        gate.accept({'sequence': 2, 'action': 'watch', 'challenge': fresh, 'age_ms': 0})
        self.assertTrue(gate.active)

    def test_passive_scan_cannot_begin_fixed_trial_without_fresh_watch(self):
        class Clock:
            t = 0.
            def __call__(self):
                self.t += .02
                return self.t
        class Driver:
            def start(self): pass
            def running(self): return True
        class Link:
            received_counts = {'scan': 3, 'odom': 3}
            def spin(self, _): pass
            def fresh(self): pass
            def fresh_scan(self): pass
        class NoInput:
            def receive(self): return None
        clock = Clock()
        gate = InputGate(clock)
        with self.assertRaisesRegex(ValueError, 'SAME_WINDOW_SCAN_OR_ODOM_NOT_READY'):
            wait_for_same_window_inputs(Link(), NoInput(), lambda _: None,
                                        gate, clock, Driver())

    def test_fresh_watch_after_warmup_allows_only_guarded_trial_entry(self):
        class Clock:
            t = 0.
            def __call__(self):
                self.t += .01
                return self.t
        class Driver:
            def start(self):
                self.started = True
            def running(self): return True
        class Link:
            received_counts = {'scan': 3, 'odom': 3}
            require_scan_fresh = False
            def spin(self, _): pass
            def fresh(self): pass
            def fresh_scan(self): pass
        clock = Clock()
        gate = InputGate(clock)
        initial = gate.challenge()
        gate.accept({'sequence': 1, 'action': 'qualify', 'challenge': initial, 'age_ms': 0})
        gate.suspend_for_sensor_warmup()
        outputs = []
        class Input:
            sent = False
            def receive(self):
                if outputs and outputs[-1]['state'] == 'TESTING' and not self.sent:
                    self.sent = True
                    return {'sequence': 2, 'action': 'watch',
                            'challenge': outputs[-1]['challenge'], 'age_ms': 0}
                return None
        link = Link()
        safety = wait_for_same_window_inputs(link, Input(), outputs.append, gate, clock, Driver())
        self.assertEqual(outputs[0]['state'], 'PREPARING')
        self.assertTrue(gate.active)
        self.assertTrue(link.require_scan_fresh)
        safety()

    def test_early_warmup_watch_cannot_expire_session_or_authorize_later_motion(self):
        class Clock:
            t = 0.
            def __call__(self):
                self.t += .01
                return self.t
        class Driver:
            def start(self): pass
            def running(self): return True
        class Link:
            received_counts = {'scan': 0, 'odom': 3}
            ticks = 0
            require_scan_fresh = False
            def spin(self, _):
                self.ticks += 1
                if self.ticks == 30:self.received_counts['scan'] = 3
            def fresh(self): pass
            def fresh_scan(self): pass
        clock = Clock()
        gate = InputGate(clock)
        nonce = gate.challenge()
        gate.accept({'sequence': 1, 'action': 'qualify', 'challenge': nonce, 'age_ms': 0})
        gate.suspend_for_sensor_warmup()
        outputs = []
        class Input:
            sent = False
            def receive(self):
                if not self.sent and outputs and outputs[-1]['state'] == 'TESTING':
                    self.sent = True
                    return {'sequence': 2, 'action': 'watch',
                            'challenge': outputs[-1]['challenge'], 'age_ms': 0}
                return None
        link = Link()
        with self.assertRaisesRegex(ValueError, 'SAME_WINDOW_SCAN_OR_ODOM_NOT_READY'):
            wait_for_same_window_inputs(link, Input(), outputs.append, gate, clock, Driver())
        self.assertEqual(link.received_counts['scan'], 3)
        self.assertFalse(gate.active)
        self.assertFalse(link.require_scan_fresh)

    def test_warmup_repeated_fresh_watch_can_enter_only_after_scan_ready(self):
        class Clock:
            t = 0.
            def __call__(self):
                self.t += .01
                return self.t
        class Driver:
            def start(self): pass
            def running(self): return True
        class Link:
            received_counts = {'scan': 0, 'odom': 3}
            ticks = 0
            require_scan_fresh = False
            def spin(self, _):
                self.ticks += 1
                if self.ticks == 30:self.received_counts['scan'] = 3
            def fresh(self): pass
            def fresh_scan(self): pass
        clock = Clock()
        gate = InputGate(clock)
        nonce = gate.challenge()
        gate.accept({'sequence': 1, 'action': 'qualify', 'challenge': nonce, 'age_ms': 0})
        gate.suspend_for_sensor_warmup()
        outputs = []
        class Input:
            last_challenge = None
            sequence = 1
            def receive(self):
                if not outputs or outputs[-1]['state'] != 'TESTING':return None
                challenge = outputs[-1]['challenge']
                if challenge == self.last_challenge:return None
                self.last_challenge = challenge
                self.sequence += 1
                return {'sequence': self.sequence, 'action': 'watch',
                        'challenge': challenge, 'age_ms': 0}
        link = Link()
        wait_for_same_window_inputs(link, Input(), outputs.append, gate, clock, Driver())
        self.assertGreaterEqual(link.ticks, 30)
        self.assertTrue(gate.active)
        self.assertEqual(gate.last_action, 'watch')
        self.assertTrue(link.require_scan_fresh)

    def test_reviewed_release_bundle_contains_combined_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'release.tar'
            bundle(archive)
            with tarfile.open(archive) as source:
                names = source.getnames()
            self.assertIn('isolated_ros_scan.py', names)
            self.assertIn('teleop_worker.py', names)

    def fixture(self, path, *, static=True, dynamic=True, scan=True):
        clock = iter((100, 200, 300, 400, 500, 600, 700, 800))
        record = RawRosRecorder(path, serializer=lambda value: value,
                                monotonic_ns=lambda: next(clock))
        record.record('guarded_cmd_vel', b'command')
        record.record('odom', b'odom')
        if scan:
            record.record('scan', b'scan')
        if dynamic:
            record.record('/tf', b'tf')
        if static:
            record.record('/tf_static', b'static')
        record.record('guarded_cmd_vel', b'command2')
        record.close()

    def test_complete_same_command_window_keeps_alignment_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'ros-messages.raw'
            self.fixture(raw)
            report = {'mode': 'qualify_scan', 'robot_session_id': 'manual-' + 'a'*32,
                      'boot_id': 'boot', 'release_id': 'release',
                      'received_counts': {'scan': 1, 'odom': 1, '/tf': 1, '/tf_static': 1},
                      'moving_command_ns': [100, 600]}
            receipt = {'status': 'COMPLETE', 'binding': 'VERIFIED',
                       'robot_session_id': report['robot_session_id']}
            result = inspect(report, raw, receipt)
            self.assertEqual(result['status'], 'COMMAND_WINDOW_RAW_CAPTURED_UNALIGNED')
            self.assertFalse(result['alignment_verified'])
            self.assertFalse(result['physical_motion_verified'])

    def test_missing_static_tf_is_an_explicit_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'ros-messages.raw'
            self.fixture(raw, static=False)
            report = {'mode': 'qualify_scan', 'robot_session_id': 'manual-' + 'a'*32,
                      'received_counts': {'scan': 1, 'odom': 1, '/tf': 1, '/tf_static': 0},
                      'moving_command_ns': [100, 500]}
            receipt = {'status': 'COMPLETE', 'binding': 'VERIFIED',
                       'robot_session_id': report['robot_session_id']}
            self.assertEqual(inspect(report, raw, receipt)['reason'], 'STATIC_TF_NOT_CAPTURED')

    def test_mismatched_export_or_missing_raw_cannot_pass(self):
        report = {'mode': 'qualify_scan', 'robot_session_id': 'manual-' + 'a'*32,
                  'moving_command_ns': [100, 500]}
        self.assertEqual(inspect(report, Path('missing'), {})['reason'],
                         'EVIDENCE_EXPORT_OR_CONTEXT_INCOMPLETE')

    def test_report_topic_counts_must_match_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'ros-messages.raw'
            self.fixture(raw)
            report = {'mode': 'qualify_scan', 'robot_session_id': 'manual-' + 'a'*32,
                      'moving_command_ns': [100, 600],
                      'received_counts': {'scan': 2, 'odom': 1, '/tf': 1, '/tf_static': 1}}
            receipt = {'status': 'COMPLETE', 'binding': 'VERIFIED',
                       'robot_session_id': report['robot_session_id']}
            self.assertEqual(inspect(report, raw, receipt)['reason'],
                             'ROBOT_REPORT_RAW_TOPIC_COUNT_MISMATCH')

    def test_driver_never_starts_without_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = IsolatedRosScan(Path(directory) / 'driver.log')
            with patch.object(isolated_ros_scan, 'BINARY', Path(directory) / 'missing-driver'), self.assertRaisesRegex(
                    RuntimeError, 'ISOLATED_DRIVER_BINARY_MISSING'):
                driver.start()
            self.assertIsNone(driver.child)
            self.assertEqual(driver.stop()['sensor_stop']['status'], 'NOT_RUN')

    def test_driver_child_gets_pinned_library_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = IsolatedRosScan(Path(directory) / 'driver.log')
            with patch.object(isolated_ros_scan, 'binary_identity'), patch.object(
                    isolated_ros_scan.subprocess, 'Popen', return_value=SimpleNamespace()) as launch:
                driver.start()
            driver.stream.close()
            self.assertEqual(launch.call_count, 1)
            paths = launch.call_args.kwargs['env']['LD_LIBRARY_PATH'].split(isolated_ros_scan.os.pathsep)
            self.assertEqual(paths[0], str(isolated_ros_scan.DRIVER_LIB.parent))
            self.assertIn('/opt/ros/humble/lib', paths)

    def test_owned_driver_reaped_before_independent_sensor_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = IsolatedRosScan(Path(directory) / 'driver.log')
            driver.child = SimpleNamespace(poll=lambda: 0)
            events = []
            def reap(_):
                events.append('reap')
                return {'exit_code': 0, 'signal': 'SIGINT'}
            def stop():
                events.append('sensor_stop')
                return {'write_complete': True, 'quiet_after_1s': True,
                        'port_restored': True}
            with patch.object(isolated_ros_scan, 'reap_owned', reap), patch.object(
                    isolated_ros_scan, 'explicit_sensor_stop', stop):
                result = driver.stop()
            self.assertEqual(events, ['reap', 'sensor_stop'])
            self.assertTrue(result['sensor_stop']['quiet_after_1s'])
            self.assertEqual(result['physical_rotor_stopped'], 'UNCONFIRMED')

    def test_unreaped_driver_never_competes_for_sensor_port(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = IsolatedRosScan(Path(directory) / 'driver.log')
            driver.child = SimpleNamespace(poll=lambda: None)
            with (patch.object(isolated_ros_scan, 'reap_owned', side_effect=RuntimeError('UNREAPED')),
                  patch.object(isolated_ros_scan, 'explicit_sensor_stop',
                               side_effect=AssertionError('must not open occupied serial'))):
                result = driver.stop()
            self.assertIn('UNREAPED', result['error'])
            self.assertEqual(result['sensor_stop']['status'], 'NOT_RUN')

    def test_no_motor_trial_when_driver_exits_before_scan(self):
        class Driver:
            def start(self): self.started = True
            def running(self): return False
        class Gate:
            started = 0.
            def check(self): pass
        class Link:
            def spin(self, _): raise AssertionError('Must stop before spinning')
        with self.assertRaisesRegex(ValueError, 'ISOLATED_SCAN_DRIVER_EARLY_EXIT'):
            wait_for_same_window_inputs(Link(), None, lambda _: None, Gate(), lambda: 1., Driver())

    def test_scan_freshness_requires_one_root_scan_publisher(self):
        link = teleop_ros.RosLink.__new__(teleop_ros.RosLink)
        link.received_counts = {'scan': 3}
        link.last_scan_t = 9.9
        link.node = SimpleNamespace(count_publishers=lambda topic: 0)
        with patch.object(teleop_ros.time, 'monotonic', lambda: 10.):
            with self.assertRaisesRegex(ValueError, 'ROS_SCAN_STALE_OR_PUBLISHER_UNOWNED'):
                link.fresh_scan()
            link.node.count_publishers = lambda topic: 1 if topic == '/scan' else 0
            link.fresh_scan()
            link.last_scan_t = 9.6
            with self.assertRaisesRegex(ValueError, 'ROS_SCAN_STALE_OR_PUBLISHER_UNOWNED'):
                link.fresh_scan()


if __name__ == '__main__':
    unittest.main()
