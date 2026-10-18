# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only health contract tests: no SSH, ROS, board or motion."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import robot_health as h
from check_robot_connection import payload
from turtlebot_probe import choose_topic

SNAPSHOT = '''PING id=200 comm=0 error=0 model=20480 message=ok
READ identification addr=0 len=9 comm=0 error=0 bytes=00500100000005C800
READ expected_device_status addr=18 len=1 comm=0 error=0 bytes=00
READ expected_supply_voltage addr=42 len=4 comm=0 error=0 bytes=65040000
READ expected_wheel_feedback addr=128 len=16 comm=0 error=0 bytes=0000000000000000080700009A150000
READ expected_torque_state addr=149 len=1 comm=0 error=0 bytes=00
READ expected_command_state addr=150 len=24 comm=0 error=0 bytes=000000000000000000000000000000000000000000000000
RESTORE termios=0 modem=0 modem_saved=1
'''


class RobotHealthTests(unittest.TestCase):
    def test_actual_snapshot_decode(self):
        data = h.parse_board_snapshot(SNAPSHOT)
        self.assertEqual(data['voltage_v'], 11.25)
        self.assertEqual(data['estimated_percent'], 41.7)
        self.assertEqual(data['encoders'], [1800, 5530])
        self.assertFalse(data['torque_enabled'])
        self.assertTrue(data['command_bytes_zero'])

    def test_unknown_firmware_incomplete_or_bad_restore_is_not_accepted(self):
        for text in (SNAPSHOT.replace('05C800', '06C800'),
                     SNAPSHOT.replace('termios=0', 'termios=-1'),
                     SNAPSHOT.replace('addr=149 len=1 comm=0', 'addr=149 len=1 comm=-1'),
                     SNAPSHOT + 'READ duplicate addr=149 len=1 comm=0 error=0 bytes=00\n'):
            with self.assertRaises(ValueError):
                h.parse_board_snapshot(text)

    def test_charge_boundary_and_protection_warning(self):
        data = h.parse_board_snapshot(SNAPSHOT.replace('65040000', '3E040000'))
        self.assertEqual(data['estimated_percent'], 20)
        self.assertTrue(data['charge_requested'])
        data = h.parse_board_snapshot(SNAPSHOT.replace('65040000', '4C040000'))
        self.assertFalse(data['charge_requested'])
        self.assertTrue(data['near_board_protection'])

    def test_busy_port_never_invokes_helper(self):
        with patch.dict(os.environ, TWINPULSE_BOARD_SNAPSHOT='1'), \
             patch.object(h, 'deployment', return_value={'status': 'VERIFIED'}), \
             patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2, b'BUSY: occupied', b'')) as run:
            self.assertEqual(h.board_snapshot()['status'], 'BUSY')
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-1], 'read-board')

    def test_digest_change_never_invokes_helper(self):
        with patch.dict(os.environ, TWINPULSE_BOARD_SNAPSHOT='1'), \
             patch.object(h, 'deployment', side_effect=ValueError('changed')), \
             patch.object(h.subprocess, 'run') as run:
            self.assertEqual(h.board_snapshot()['status'], 'UNKNOWN')
            run.assert_not_called()

    def test_helper_timeout_fails_unknown_no_retry(self):
        with patch.dict(os.environ, TWINPULSE_BOARD_SNAPSHOT='1'), \
             patch.object(h, 'deployment', return_value={'status': 'VERIFIED'}), \
             patch.object(h.subprocess, 'run', side_effect=subprocess.TimeoutExpired('helper', 20)) as run:
            self.assertEqual(h.board_snapshot()['status'], 'UNKNOWN')
            self.assertEqual(run.call_count, 1)

    def test_health_is_not_motion_permission(self):
        data = {'board': h.parse_board_snapshot(SNAPSHOT), 'processes': [],
                'guard_artifact_verified': True, 'motion_authorized': False}
        self.assertEqual(h.summarize_health(data)['status'], 'IDLE_SNAPSHOT_OK')
        self.assertFalse(data['motion_authorized'])
        data['board']['torque_enabled'] = True
        self.assertEqual(h.summarize_health(data)['status'], 'NEEDS_ATTENTION')

    def test_unknown_board_does_not_inherit_last_battery(self):
        data = {'board': {'status': 'UNKNOWN'}, 'processes': [], 'guard_artifact_verified': True}
        self.assertEqual(h.summarize_health(data)['status'], 'NEEDS_ATTENTION')
        self.assertNotIn('voltage_v', data['board'])

    def test_bundled_health_and_explicit_board_opt_in(self):
        script = payload('humble', 86, True, True)
        self.assertIn('export TWINPULSE_HEALTH=1', script)
        self.assertIn('export TWINPULSE_BOARD_SNAPSHOT=1', script)
        self.assertIn('def health_snapshot(board=None)', script)
        with self.assertRaises(ValueError):
            payload('humble', 86, False, True)

    def test_multiple_topics_are_ambiguous_even_with_root_topic(self):
        msg = 'sensor_msgs/msg/LaserScan'
        self.assertIsNone(choose_topic([('/scan', [msg]), ('/other/scan', [msg])], '/scan', msg))


if __name__ == '__main__':
    unittest.main()
