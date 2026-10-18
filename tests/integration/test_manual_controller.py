# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure fake-clock/controller and owned-loopback tests. No robot transport exists."""
import unittest
from tests.integration import test_r5_product_api as r5
from twinpulse_app.manual_controller import ManualController
from twinpulse_app.command_broker import BrokerError


class ManualControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.
        self.control = ManualController(clock=lambda: self.now, wall=lambda: self.now * 1000)
        self.session = self.control.begin('owner', 'rehearsal', True)['session_id']
        self.seq = 0

    def tearDown(self): self.control.close()

    def send(self, action):
        self.seq += 1
        return self.control.command('owner', self.session, self.seq, action, self.now * 1000 + 250)

    def test_physical_mode_is_not_unlockable_by_confirmation_or_good_state(self):
        for mode in ['physical', 'live', True, {}, None]:
            with self.assertRaises(BrokerError): self.control.begin('owner', mode, True)
        self.assertFalse(self.control.snapshot('owner')['physical_motion_authorized'])
        self.assertFalse(self.control.snapshot('owner')['physical_lidar_authorized'])

    def test_direction_mapping_and_release(self):
        for action, speeds in [('forward', (.03, 0)), ('backward', (-.03, 0)), ('left', (0, .2)), ('right', (0, -.2))]:
            result = self.send(action)
            self.assertEqual((result['linear_m_s'], result['angular_rad_s']), speeds)
            self.now += .1
            result = self.send('stop')
            self.assertEqual(result['linear_m_s'], 0)
            self.assertEqual(result['angular_rad_s'], 0)
            self.assertTrue(result['armed'])

    def test_lost_input_expires_without_status_poll_and_cannot_resume(self):
        self.send('forward'); self.now += .4
        self.control._tick()
        result = self.control.snapshot('owner')
        self.assertEqual(result['reason'], 'INPUT_EXPIRED')
        self.assertFalse(result['armed'])
        self.assertAlmostEqual(result['pose']['x_m'], .03 * .25)
        with self.assertRaises(BrokerError): self.send('forward')

    def test_continuous_hold_cannot_extend_two_second_limit(self):
        for _ in range(20):
            self.send('left'); self.now += .1
        self.now += .01
        self.assertFalse(self.control.snapshot('owner')['armed'])

    def test_lidar_start_does_not_extend_limit_and_stop_all_latches(self):
        self.send('lidar_start'); self.now += 7
        self.send('lidar_start'); self.now += 1.01
        self.assertFalse(self.control.snapshot('owner')['lidar_running'])
        self.send('lidar_start')
        self.assertFalse(self.send('stop_all')['lidar_running'])
        with self.assertRaises(BrokerError): self.send('lidar_start')

    def test_old_packet_cannot_override_new_stop(self):
        self.send('forward'); stopped = self.send('stop_all')
        with self.assertRaises(BrokerError):
            self.control.command('owner', self.session, 1, 'forward', self.now * 1000 + 200)
        self.assertEqual(self.control.snapshot('owner')['linear_m_s'], 0)
        self.assertFalse(stopped['armed'])

    def test_stale_and_invalid_inputs_fail_closed(self):
        with self.assertRaises(BrokerError):
            self.control.command('owner', self.session, 1, 'forward', self.now * 1000 - 1)
        self.assertFalse(self.control.snapshot('owner')['armed'])
        for sequence, action in [(True, 'forward'), (0, 'forward'), (2, 'shell'), (2, {})]:
            with self.assertRaises(BrokerError):
                self.control.command('owner', self.session, sequence, action, self.now * 1000 + 250)

    def test_ownership_rearm_close_and_session_timeout(self):
        with self.assertRaises(BrokerError): self.control.begin('other', 'rehearsal', True)
        with self.assertRaises(BrokerError): self.control.command('other', self.session, 1, 'stop', 0)
        self.now += 61
        self.assertFalse(self.control.snapshot('owner')['armed'])
        fresh = self.control.begin('owner', 'rehearsal', True)
        self.assertNotEqual(fresh['session_id'], self.session)
        self.control.close()
        with self.assertRaises(BrokerError): self.control.begin('owner', 'rehearsal', True)


class ManualControllerHttpTests(unittest.TestCase):
    request = r5.R5ProductApiTests.request
    setUp = r5.R5ProductApiTests.setUp
    tearDown = r5.R5ProductApiTests.tearDown

    def test_http_confirmation_csrf_shape_and_physical_rejection(self):
        path = '/v1/product/robot/controller'
        headers = {'Cookie': self.cookie, 'X-TwinPulse-CSRF': self.csrf, 'Origin': self.server.base_url}
        self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.request(path+'/session', {'mode': 'rehearsal', 'confirmed': True}, headers={'Cookie': self.cookie})[0], 403)
        self.assertEqual(self.request(path+'/session', {'mode': 'physical', 'confirmed': True}, headers=headers)[0], 409)
        code, session, _ = self.request(path+'/session', {'mode': 'rehearsal', 'confirmed': True}, headers=headers)
        self.assertEqual(code, 200)
        self.assertFalse(session['physical_motion_authorized'])
        self.assertEqual(self.request(path+'/input', {'arbitrary_command': 'x'}, headers=headers)[0], 400)
        body = {'session_id': session['session_id'], 'sequence': 1, 'action': 'stop_all', 'expires_at_ms': 0}
        self.assertEqual(self.request(path+'/input', body, headers=headers)[0], 200)
        self.assertFalse(self.request(path, headers=headers)[1]['armed'])


if __name__ == '__main__': unittest.main()
