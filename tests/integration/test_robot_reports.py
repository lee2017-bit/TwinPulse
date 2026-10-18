# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline recorded-health review. No device access or robot subprocesses."""
from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
# Test this standard-library-only boundary on the minimal WSL robot verifier.
# The Windows HTTP integration separately tests the actual package composition,
# which legitimately needs the App's Pillow image dependency.
spec = importlib.util.spec_from_file_location('robot_reports_pure',
    ROOT / 'packages/twinpulse_app/src/twinpulse_app/robot_reports.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RobotReports = module.RobotReports


def report():
    return {'schema_version': 'robot-health-1.0', 'observed_at_utc': '2026-09-26T15:00:00Z',
            'boot_id': '76d5f5c5-0a06-4720-aa6a-7b328d6d6265', 'motion_authorized': False,
            'guard_artifact_verified': True, 'deployment': {'release_id': 'a' * 64},
            'board': {'status': 'OBSERVED', 'observed_at_utc': '2026-09-26T15:00:01Z',
                      'voltage_v': 11.21, 'estimated_percent': 99, 'torque_enabled': False,
                      'wheel_velocity_raw': [0, 0], 'command_bytes_zero': True, 'port_restored': True}}


class RobotReportTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 26, 16, tzinfo=timezone.utc)
        self.store = RobotReports(clock=lambda: self.now)

    def test_empty_not_current_or_ready(self):
        state = self.store.snapshot()
        self.assertIsNone(state['record'])
        self.assertFalse(state['motion_authorized'])
        self.assertFalse(state['demo_ready'])

    def test_good_report_is_still_unverified_historical_and_battery_recomputed(self):
        state = self.store.import_report(report())
        self.assertEqual(state['record']['battery']['estimated_percent'], 39.4)
        self.assertEqual(state['record']['age_seconds'], 3600)
        self.assertEqual(state['current_robot_state'], 'UNKNOWN')
        self.assertEqual(state['connection'], 'NOT_CONNECTED')
        self.assertFalse(state['source_verified'])
        self.assertFalse(state['motion_authorized'])
        self.assertTrue(state['record']['idle_at_observation'])

    def test_connection_wrapper_and_session_reset(self):
        state = self.store.import_report({'schema_version': 'robot-connection-1.0',
            'mode': 'read_only', 'motion_authorized': False, 'health': report()})
        self.assertIsNotNone(state['record'])
        fresh = RobotReports().snapshot()
        self.assertNotEqual(fresh['session_id'], state['session_id'])
        self.assertIsNone(fresh['record'])

    def test_no_unknown_fields_or_raw_output_retained(self):
        value = report()
        value.update(secret='CANARY-PRIVATE', raw_output='CANARY-PRIVATE', status='READY')
        value['board']['extra'] = 'CANARY-PRIVATE'
        rendered = json.dumps(self.store.import_report(value))
        self.assertNotIn('CANARY-PRIVATE', rendered)
        self.assertNotIn('READY', rendered)

    def test_invalid_import_keeps_previous_record(self):
        previous = self.store.import_report(report())['record']
        value = report(); value['motion_authorized'] = True
        with self.assertRaises(ValueError): self.store.import_report(value)
        self.assertEqual(self.store.snapshot()['record'], previous)

    def test_invalid_fields_rejected(self):
        for field, value in [('boot_id', '../robot'), ('guard_artifact_verified', 'true'),
                             ('observed_at_utc', '2026-09-26T15:00:00'),
                             ('observed_at_utc', '2027-01-01T00:00:00Z')]:
            with self.subTest(field=field, value=value):
                bad = report(); bad[field] = value
                with self.assertRaises(ValueError): self.store.import_report(bad)

    def test_invalid_board_fields_rejected(self):
        for field, value in [('voltage_v', float('nan')), ('voltage_v', True), ('voltage_v', 90),
                             ('wheel_velocity_raw', [False, 0]), ('torque_enabled', 0),
                             ('observed_at_utc', '2026-09-26T14:00:00Z')]:
            with self.subTest(field=field, value=value):
                bad = report(); bad['board'][field] = value
                with self.assertRaises(ValueError): self.store.import_report(bad)

    def test_unknown_busy_and_not_requested_are_not_idle(self):
        for status in ('UNKNOWN', 'BUSY', 'NOT_REQUESTED'):
            value = report(); value['board'] = {'status': status}
            record = self.store.import_report(value)['record']
            self.assertIsNone(record['battery']); self.assertIsNone(record['idle_at_observation'])

    def test_motion_observation_never_idle(self):
        for field, value in [('torque_enabled', True), ('command_bytes_zero', False),
                             ('port_restored', False), ('wheel_velocity_raw', [1, 0])]:
            bad = report(); bad['board'][field] = value
            self.assertFalse(self.store.import_report(bad)['record']['idle_at_observation'])

    def test_each_failed_idle_condition_is_preserved_without_guessing(self):
        for field, value, reason in [('torque_enabled', True, 'TORQUE_ENABLED'),
                ('command_bytes_zero', False, 'COMMAND_NONZERO'),
                ('port_restored', False, 'PORT_RESTORE_UNCONFIRMED'),
                ('wheel_velocity_raw', [1, 0], 'WHEEL_VELOCITY_NONZERO')]:
            with self.subTest(field=field):
                source = report(); source['board'][field] = value
                result = self.store.import_report(source)['record']
                self.assertEqual(result['idle_failure_reasons'], [reason])
                self.assertEqual(result['board_observation'][field], value)
                self.assertFalse(result['idle_at_observation'])

    def test_unknown_board_has_no_invented_details_and_all_failures_accumulate(self):
        source = report()
        source['board'].update(torque_enabled=True, command_bytes_zero=False,
                               port_restored=False, wheel_velocity_raw=[1, -1])
        result = self.store.import_report(source)['record']
        self.assertEqual(len(result['idle_failure_reasons']), 4)
        source['board'] = {'status': 'UNKNOWN', 'torque_enabled': False}
        result = self.store.import_report(source)['record']
        self.assertIsNone(result['board_observation'])
        self.assertIsNone(result['idle_at_observation'])
        self.assertEqual(result['idle_failure_reasons'], [])

    def test_board_details_are_deep_copied_and_unknown_data_not_retained(self):
        source = report()
        result = self.store.import_report(source)['record']
        self.assertEqual(result['idle_failure_reasons'], [])
        source['board']['wheel_velocity_raw'][0] = 999
        result['board_observation']['wheel_velocity_raw'][1] = 888
        self.assertEqual(self.store.snapshot()['record']['board_observation']['wheel_velocity_raw'], [0, 0])

    def test_result_copy_and_dynamic_age(self):
        value = self.store.import_report(report()); value['record']['boot_id'] = 'changed'
        self.now += timedelta(seconds=100)
        self.assertEqual(self.store.snapshot()['record']['age_seconds'], 3700)
        self.assertNotEqual(self.store.snapshot()['record']['boot_id'], 'changed')

    def test_payload_limit(self):
        value = report(); value['extra'] = 'x' * 262144
        with self.assertRaises(ValueError): self.store.import_report(value)

    def test_protection_and_charge_are_separate(self):
        value = report(); value['board']['voltage_v'] = 11.0
        battery = self.store.import_report(value)['record']['battery']
        self.assertTrue(battery['near_protection_at_observation'])
        self.assertFalse(battery['charge_requested_at_observation'])
        value['board']['voltage_v'] = 10.86
        self.assertTrue(self.store.import_report(value)['record']['battery']['charge_requested_at_observation'])


if __name__ == '__main__':
    unittest.main()
