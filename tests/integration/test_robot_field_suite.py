# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device branch tests for the single field-session entry point."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import run_robot_field_suite as suite


def observed(voltage=12.2, torque=False):
    return {'health': {'board': {'status': 'OBSERVED', 'voltage_v': voltage,
                                 'torque_enabled': torque, 'wheel_velocity_raw': [0, 0],
                                 'command_bytes_zero': True},
                       'boot_id': 'boot-a', 'deployment': {'release_id': 'release-a'}}}


def prepared():
    return {'steps': {'source_and_idle': {'status': 'SOFTWARE_PREPARED_IDLE'},
                      'stationary_collection': {'status': 'STATIONARY_CHECK_PASS'}},
            'boot_id': 'boot-a', 'release_id': 'release-a'}


class FieldSuiteTests(unittest.TestCase):
    def run_fake(self, *, field=True, allow_off=True, act=True,
                 health_values=None, prep=None, qualified=None, scan=None):
        calls = []
        values = iter(health_values or [observed(torque=True), observed(), observed(), observed()])

        def health(*_args, **_kwargs):
            calls.append('health')
            return next(values)

        def stationary(*_args):
            calls.append('stationary')
            return prep if prep is not None else prepared(), Path('stationary')

        def qualification():
            calls.append('qualification')
            return qualified if qualified is not None else {
                'status': 'QUALIFIED', 'robot_boot_id': 'boot-a',
                'robot_release_id': 'release-a'}

        def scan_client(**_kwargs):
            calls.append('scan')
            return scan if scan is not None else {'status': 'ROS_SCAN_CAPTURED_PHYSICAL_STOP_UNCONFIRMED'}, Path('scan')

        with tempfile.TemporaryDirectory(dir=suite.ROOT / 'artifacts') as directory:
            report, path = suite.run_suite(field_run=field, operator_watching=field,
                                           clear_floor=field, allow_torque_off=allow_off,
                                           allow_fixed_motion_and_scan=act,
                                           output=Path(directory) / 'result',
                                           preflight=lambda: {'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'},
                                           health=health, stationary=stationary,
                                           qualification=qualification, scan=scan_client)
            self.assertTrue((path / 'report.json').is_file())
        return report, calls

    def test_offline_default_never_contacts_robot(self):
        report, calls = self.run_fake(field=False, allow_off=False, act=False)
        self.assertEqual(calls, [])
        self.assertEqual(report['stages']['initial_health']['status'], 'SKIPPED')
        self.assertFalse(report['demo_ready'])

    def test_preflight_failure_blocks_all_ssh_but_keeps_saved_diagnostics(self):
        with tempfile.TemporaryDirectory(dir=suite.ROOT / 'artifacts') as directory:
            report, _ = suite.run_suite(field_run=True, operator_watching=True,
                                        clear_floor=True, output=Path(directory) / 'result',
                                        preflight=lambda: {'status': 'FAILED'},
                                        health=lambda *_a, **_k: self.fail('ssh'))
        self.assertEqual(report['status'], 'FIELD_BLOCKED_PC_PREFLIGHT')
        self.assertEqual(report['stages']['saved_evidence']['status'], 'NOT_REQUESTED')

    def test_initial_read_only_health_uses_pinned_field_identity(self):
        seen = []
        with tempfile.TemporaryDirectory(dir=suite.ROOT / 'artifacts') as directory:
            report, _ = suite.run_suite(field_run=True, operator_watching=True,
                                        clear_floor=True, output=Path(directory) / 'result',
                                        preflight=lambda: {'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'},
                                        health=lambda *_args, **kwargs: (seen.append(kwargs['identity_file'])
                                                                          or {'status': 'SSH_OR_REMOTE_SETUP_FAILED',
                                                                              'reason': 'auth'}))
        self.assertEqual(seen, [Path.home() / '.ssh/twinpulse-burger/id_ed25519_automation'])
        self.assertEqual(report['stages']['initial_health']['reason'], 'auth')

    def test_invalid_saved_raw_remains_failed_without_contact(self):
        with tempfile.TemporaryDirectory(dir=suite.ROOT / 'artifacts') as directory:
            report, _ = suite.run_suite(output=Path(directory) / 'result',
                                        saved_raw=[Path(directory) / 'ros-messages.raw'],
                                        preflight=lambda: {'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'},
                                        health=lambda *_a, **_k: self.fail('ssh'))
        self.assertEqual(report['stages']['saved_evidence']['status'], 'FAILED')
        self.assertFalse(report['demo_ready'])

    def test_torque_on_can_use_one_approved_off_and_continue(self):
        report, calls = self.run_fake()
        self.assertEqual(calls.count('qualification'), 1)
        self.assertEqual(calls.count('scan'), 1)
        self.assertEqual(report['stages']['prepare_stationary']['status'], 'PASS')
        self.assertFalse(report['demo_ready'])

    def test_qualification_failure_does_not_hide_independent_scan(self):
        report, calls = self.run_fake(qualified={'status': 'FAILED', 'reason': 'STOP_UNSTABLE',
                                                 'result': {'cleanup_confirmed': True},
                                                 'robot_boot_id': 'boot-a',
                                                 'robot_release_id': 'release-a'})
        self.assertEqual(report['stages']['qualification']['status'], 'FAILED')
        self.assertIn('scan', calls)
        self.assertEqual(report['stages']['ros_scan']['status'],
                         'ROS_SCAN_CAPTURED_PHYSICAL_STOP_UNCONFIRMED')

    def test_combined_capture_never_restarts_sensor_for_second_scan(self):
        combined = {'status': 'QUALIFIED', 'robot_boot_id': 'boot-a',
                    'robot_release_id': 'release-a', 'result': {'cleanup_confirmed': True},
                    'diagnosis': {
                        'same_window': {'status': 'COMMAND_WINDOW_RAW_CAPTURED_UNALIGNED',
                                        'full_session_counts': {'scan': 5}, 'reason': None},
                        'scan_driver_cleanup': {'sensor_stop': {'write_complete': True,
                                                                 'quiet_after_1s': True,
                                                                 'port_restored': True}}}}
        report, calls = self.run_fake(qualified=combined)
        self.assertEqual(calls.count('qualification'), 1)
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['ros_scan']['status'], 'SAME_SESSION_RAW_CAPTURED')
        self.assertFalse(report['demo_ready'])

    def test_combined_driver_stop_uncertain_never_retries(self):
        combined = {'status': 'FAILED', 'robot_boot_id': 'boot-a',
                    'robot_release_id': 'release-a', 'result': {'cleanup_confirmed': True},
                    'diagnosis': {'same_window': {'status': 'INCOMPLETE',
                                                  'full_session_counts': {'scan': 0},
                                                  'reason': 'STATIC_TF_NOT_CAPTURED'},
                                  'scan_driver_cleanup': {'sensor_stop': {'write_complete': False}}}}
        report, calls = self.run_fake(qualified=combined)
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['ros_scan']['status'], 'NEEDS_REVIEW')

    def test_battery_guard_failure_stops_other_power_using_trial(self):
        report, calls = self.run_fake(qualified={'status': 'FAILED',
                                                 'reason': 'BATTERY_BUTTON_OR_SOURCE_AGE',
                                                 'result': {'cleanup_confirmed': True},
                                                 'robot_boot_id': 'boot-a',
                                                 'robot_release_id': 'release-a'})
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['ros_scan']['status'], 'SKIPPED')

    def test_unconfirmed_qualification_cleanup_blocks_sensor(self):
        report, calls = self.run_fake(qualified={'status': 'FAILED', 'reason': 'STOP_UNSTABLE',
                                                 'result': {'cleanup_confirmed': False},
                                                 'robot_boot_id': 'boot-a',
                                                 'robot_release_id': 'release-a'})
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['ros_scan']['reason'],
                         'QUALIFICATION_CLEANUP_NOT_CONFIRMED')

    def test_low_pre_motion_voltage_skips_movement_but_allows_sensor(self):
        report, calls = self.run_fake(health_values=[observed(torque=True), observed(11.25),
                                                     observed(11.25), observed(11.25)])
        self.assertNotIn('qualification', calls)
        self.assertIn('scan', calls)
        self.assertEqual(report['stages']['qualification']['status'], 'SKIPPED')

    def test_unknown_motion_state_blocks_sensor(self):
        report, calls = self.run_fake(qualified={'status': 'REMOTE_STATE_UNKNOWN'},
                                      health_values=[observed(torque=True), observed(),
                                                     observed(), observed()])
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['ros_scan']['status'], 'SKIPPED')

    def test_changed_boot_before_motion_skips_both_physical_trials(self):
        changed = observed()
        changed['health']['boot_id'] = 'boot-b'
        report, calls = self.run_fake(health_values=[observed(torque=True), changed,
                                                     observed(), observed()])
        self.assertNotIn('qualification', calls)
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['qualification']['status'], 'SKIPPED')

    def test_qualification_report_binding_mismatch_blocks_scan(self):
        report, calls = self.run_fake(qualified={'status': 'QUALIFIED',
                                                 'robot_boot_id': 'boot-b',
                                                 'robot_release_id': 'release-a',
                                                 'result': {'cleanup_confirmed': True}})
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['ros_scan']['reason'],
                         'QUALIFICATION_BOOT_RELEASE_MISMATCH')

    def test_stationary_failure_still_gets_final_readonly_health(self):
        report, calls = self.run_fake(prep={'status': 'FAILED'},
                                      health_values=[observed(torque=True), observed(), observed()])
        self.assertNotIn('qualification', calls)
        self.assertNotIn('scan', calls)
        self.assertEqual(report['stages']['final_health']['status'], 'OBSERVED')

    def test_malformed_initial_board_skips_preparation_without_retry(self):
        broken = observed()
        broken['health']['board']['wheel_velocity_raw'] = None
        report, calls = self.run_fake(health_values=[broken], act=True)
        self.assertEqual(calls, ['health'])
        self.assertEqual(report['stages']['prepare_stationary']['status'], 'SKIPPED')

    def test_scope_and_target_must_be_explicit(self):
        with self.assertRaisesRegex(ValueError, 'CURRENT_OPERATOR'):
            suite.run_suite(field_run=True)
        with self.assertRaisesRegex(ValueError, 'CANNOT_BE_OVERRIDDEN'):
            suite.run_suite(field_run=True, operator_watching=True, clear_floor=True,
                            allow_fixed_motion_and_scan=True, host='192.168.35.140')


if __name__ == '__main__':
    unittest.main()
