# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No devices: collector is always replaced; HTTP is owned loopback only."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
import importlib.util

from tests.integration import test_r5_product_api as r5
from tests.integration.test_robot_reports import report
from twinpulse_app.robot_diagnostics import RobotDiagnostics
from twinpulse_app.command_broker import BrokerError

ROOT = r5.ROOT


def observation():
    value = report()
    now = datetime.now(timezone.utc).isoformat()
    value['observed_at_utc'] = value['board']['observed_at_utc'] = now
    value['status'] = 'IDLE_SNAPSHOT_OK'
    return {'schema_version': 'robot-connection-1.0', 'mode': 'read_only',
            'motion_authorized': False, 'status': 'NO_SENSOR_DATA', 'health': value}


def fixture(root, collect, clock=lambda: 1):
    (root/'scripts').mkdir()
    for name in ('check_robot_connection.py', 'robot_health.py', 'turtlebot_probe.py'):
        shutil.copyfile(ROOT/'scripts'/name, root/'scripts'/name)
    key, hosts = root/'fixture-identity', root/'fixture-hosts'
    key.write_text('NOT A KEY: offline fixture')
    hosts.write_text('NOT A HOST: offline fixture')
    return RobotDiagnostics(root, identity=key, known_hosts=hosts, collector=collect,
                            which=lambda _: 'fixture-ssh', clock=clock)


class RobotDiagnosticsTests(unittest.TestCase):
    def test_failure_preserves_safe_specific_cause_and_exit_without_private_stderr(self):
        self.service._collector=lambda *a,**k:{'status':'SSH_OR_REMOTE_SETUP_FAILED','exit_code':255,
            'reason':'PRIVATE_CANARY identity path: ssh: connect to host: Connection refused'}
        self.service.start('owner',self.ready(),True)
        done=self.finish()
        self.assertEqual(done['job']['diagnostic'],{'code':'SSH_CONNECTION_REFUSED','exit_code':255})
        saved=json.loads((self.root/'artifacts/robot-console'/done['job']['id']/'report.json').read_text())
        self.assertEqual(saved['diagnostic'],done['job']['diagnostic'])
        self.assertNotIn('PRIVATE_CANARY',json.dumps(saved))
        self.assertIsNone(done['record'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.calls = []
        self.release = Event()
        self.now = 1
        def collect(*args, **kwargs):
            self.calls.append((args, kwargs))
            self.release.wait(2)
            return observation()
        self.service = fixture(self.root, collect, lambda: self.now)

    def tearDown(self):
        self.release.set()
        self.service.close()
        self.temp.cleanup()

    def ready(self):
        return self.service.preflight('owner')['start_token']

    def test_lightweight_launcher_pc_only_has_no_transport(self):
        spec = importlib.util.spec_from_file_location('console_launcher_test', ROOT/'scripts/launch_robot_console.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with patch.object(launcher, 'RobotDiagnostics', return_value=self.service), \
             patch.object(launcher.sys, 'argv', ['console', '--pc-only']), \
             patch.object(launcher.webbrowser, 'open') as opened:
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(self.calls, [])
        opened.assert_not_called()

    def test_lightweight_launcher_real_local_lifecycle_without_robot_or_engine(self):
        spec = importlib.util.spec_from_file_location('console_launcher_test', ROOT/'scripts/launch_robot_console.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        dist = self.root/'apps/twinpulse-web/dist'
        dist.mkdir(parents=True)
        (dist/'index.html').write_text('<!doctype html><title>fixture</title>')
        with patch.object(launcher, 'ROOT', self.root), \
             patch.object(launcher, 'RobotDiagnostics', return_value=self.service), \
             patch.object(launcher.sys, 'argv', ['console']), \
             patch.object(launcher.webbrowser, 'open', return_value=True) as opened, \
             patch('builtins.print') as printed, \
             patch.object(launcher, 'Event') as stop:
            stop.return_value.wait.side_effect = KeyboardInterrupt
            self.assertEqual(launcher.main(), 0)
        messages='\n'.join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn('One read-only connection check starts after browser session opens.', messages)
        self.assertIn('A read-only check does not enable movement.', messages)
        self.assertNotIn('Use PC preparation first.', messages)
        self.assertEqual(self.calls, [])
        self.assertTrue(opened.call_args.args[0].startswith('http://127.0.0.1:'))
        self.assertIn('/#robot-console=1&bootstrap=', opened.call_args.args[0])
        self.assertNotIn('/?robot-console=', opened.call_args.args[0])
        self.assertTrue(self.service._closed)

    def finish(self):
        self.release.set()
        self.service._thread.join(3)
        self.assertFalse(self.service._thread.is_alive())
        return self.service.snapshot('owner')

    def test_snapshot_preflight_never_connect_and_key_not_read(self):
        self.assertIsNone(self.service.snapshot('owner')['record'])
        with unittest.mock.patch.object(Path, 'read_bytes', autospec=True,
                side_effect=lambda p: b'code' if p.parent.name == 'scripts' else (_ for _ in ()).throw(AssertionError('key read'))):
            self.assertTrue(self.ready())
        self.assertEqual(self.calls, [])

    def test_missing_prerequisite_and_expiry_and_wrong_owner(self):
        token = self.ready()
        for owner, confirmed in [('other', True), ('owner', False), ('owner', 'true')]:
            with self.assertRaises(BrokerError): self.service.start(owner, token, confirmed)
        self.now = 122
        with self.assertRaises(BrokerError): self.service.start('owner', token, True)
        self.service.identity.unlink()
        self.assertIsNone(self.ready())
        self.assertEqual(self.calls, [])

    def test_source_change_requires_new_preflight(self):
        token = self.ready()
        with (self.root/'scripts/robot_health.py').open('a') as stream: stream.write('\n# changed')
        with self.assertRaises(BrokerError): self.service.start('owner', token, True)
        self.assertEqual(self.calls, [])

    def test_duplicate_start_single_run_and_new_run_clears_old_battery(self):
        token = self.ready()
        first = self.service.start('owner', token, True)
        self.assertEqual(self.service.start('owner', token, True)['job']['id'], first['job']['id'])
        with self.assertRaises(BrokerError): self.ready()
        done = self.finish()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], ('192.168.35.139', 'twinpulse'))
        self.assertEqual(done['job']['status'], 'COMPLETED')
        self.assertEqual(done['job']['sensor_status'], 'NO_SENSOR_DATA')
        self.assertTrue(done['job']['saved'])
        self.assertFalse(done['motion_authorized'])
        self.assertEqual(self.service.start('owner', token, True)['job']['id'], first['job']['id'])
        self.service._collector = lambda *a, **k: {'status': 'SSH_OR_REMOTE_SETUP_FAILED'}
        self.service.start('owner', self.ready(), True)
        done = self.finish()
        self.assertIsNone(done['record'])
        self.assertEqual(done['job']['status'], 'FAILED')

    def test_invalid_result_never_leaks_or_qualifies_motion(self):
        self.service._collector = lambda *a, **k: {'status': 'CANARY_SECRET', 'motion_authorized': True}
        self.service.start('owner', self.ready(), True)
        done = self.finish()
        self.assertNotIn('CANARY_SECRET', json.dumps(done))
        self.assertEqual(done['job']['status'], 'FAILED')
        self.assertFalse(done['demo_ready'])
        self.assertTrue(done['job']['saved'])
        exported=self.service.observation(done['job']['id'])
        self.assertEqual(exported['execution_id'],done['job']['execution_id'])
        self.assertNotIn('CANARY_SECRET',json.dumps(exported))

    def test_sensor_export_preserves_beams_and_is_not_hardware_proof_for_fixture(self):
        from tests.integration.test_obstacle_feedback import observation as scan
        value=observation();value['obstacle_observation']=scan()
        self.service._collector=lambda *a,**k:value
        self.service.start('owner',self.ready(),True);done=self.finish()
        exported=self.service.observation(done['job']['id'])
        self.assertEqual(exported['obstacle_observation']['scans'],scan()['scans'])
        self.assertEqual(exported['obstacle_observation']['provenance'],'IMPORTED_SENSOR')
        self.assertFalse(exported['sensor_pose_verified'])
        self.assertFalse(done['job']['authentication_verified'])
        self.assertEqual(done['job']['scan_count'],1)

    def test_original_export_keeps_float_spelling_and_import_hash(self):
        from tests.integration.test_obstacle_feedback import observation as scan
        from twinpulse_core.obstacle_feedback import checked_observation
        value=observation();source=scan()
        source['scans'][0].update(angle_min_rad=0.0,angle_increment_rad=1.0,
            range_max_m=8.0,ranges_m=[3.0,None,2.0,1.0])
        value['obstacle_observation']=source
        self.service._collector=lambda *a,**k:value
        self.service.start('owner',self.ready(),True);done=self.finish()
        exported=self.service.observation_export(done['job']['id'])
        raw=(self.root/'artifacts/robot-console'/done['job']['id']/'report.json').read_bytes()
        self.assertEqual(exported['json_text'].encode('utf-8'),raw)
        import hashlib
        self.assertEqual(exported['file_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertIn('0.0',exported['json_text'])
        self.assertEqual(checked_observation(json.loads(exported['json_text']))['scans'][0]['ranges_m'],[3.0,None,2.0,1.0])

    def test_saved_failure_contains_separate_board_fields_and_known_statuses(self):
        value = observation()
        value['health']['board']['torque_enabled'] = True
        value['health']['board']['private_extra'] = 'PRIVATE-CANARY'
        value['health']['status'] = 'NEEDS_ATTENTION'
        self.service._collector = lambda *a, **k: value
        self.service.start('owner', self.ready(), True)
        done = self.finish()
        saved = json.loads((self.root/'artifacts/robot-console'/done['job']['id']/'report.json').read_text())
        self.assertEqual(saved['schema_version'], 'robot-console-result-1.2')
        self.assertEqual(saved['execution_id'],done['job']['execution_id'])
        self.assertEqual(self.service.observation(done['job']['id'])['sha256'],saved['sha256'])
        self.assertEqual(saved['health_status'], 'NEEDS_ATTENTION')
        self.assertEqual(saved['sensor_status'], 'NO_SENSOR_DATA')
        self.assertEqual(saved['record']['idle_failure_reasons'], ['TORQUE_ENABLED'])
        self.assertEqual(saved['record']['board_observation']['wheel_velocity_raw'], [0, 0])
        self.assertTrue(saved['record']['board_observation']['torque_enabled'])
        self.assertNotIn('PRIVATE-CANARY', json.dumps(saved))
        self.assertFalse(saved['motion_authorized'])

    def test_snapshot_collected_keeps_status_but_does_not_relax_idle_gate(self):
        value = observation(); value['health']['status'] = 'SNAPSHOT_COLLECTED'
        self.service._collector = lambda *a, **k: value
        self.service.start('owner', self.ready(), True)
        done = self.finish()
        self.assertEqual(done['job']['health_status'], 'SNAPSHOT_COLLECTED')
        self.assertEqual(done['job']['result_code'], 'OBSERVATION_NEEDS_ATTENTION')

    def test_close_prevents_start(self):
        token = self.ready()
        self.service.close()
        with self.assertRaises(BrokerError): self.service.start('owner', token, True)
        self.assertEqual(self.calls, [])


class RobotDiagnosticsHttpTests(unittest.TestCase):
    request = r5.R5ProductApiTests.request

    def setUp(self):
        r5.R5ProductApiTests.setUp(self)
        self.calls = []
        def collect(*a, **k):
            self.calls.append(a)
            return observation()
        self.service = fixture(self.static, collect)
        self.server.robot_diagnostics = self.service
        self.headers = {'Cookie': self.cookie, 'X-TwinPulse-CSRF': self.csrf, 'Origin': self.server.base_url}

    def tearDown(self):
        r5.R5ProductApiTests.tearDown(self)

    def test_authenticated_csrf_exact_shape_and_no_get_side_effect(self):
        path = '/v1/product/robot/'
        self.assertEqual(self.request(path+'diagnostics')[0], 401)
        self.assertEqual(self.request(path+'preflight', {}, headers={'Cookie': self.cookie})[0], 403)
        self.assertEqual(self.request(path+'diagnostics', headers=self.headers)[0], 200)
        code, state, _ = self.request(path+'preflight', {}, headers=self.headers)
        self.assertEqual(code, 200)
        token = state['start_token']
        self.assertEqual(self.calls, [])
        body = {'start_token': token, 'confirmed_read_only': True, 'host': 'elsewhere'}
        self.assertEqual(self.request(path+'check', body, headers=self.headers)[0], 400)
        del body['host']
        code, state, _ = self.request(path+'check', body, headers=self.headers)
        self.assertEqual(code, 202)
        self.service._thread.join(3)
        code, done, _ = self.request(path+'diagnostics', headers=self.headers)
        self.assertEqual(done['job']['status'], 'COMPLETED')
        self.assertFalse(done['motion_authorized'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.request(path+'check', body, headers=self.headers)[0], 202)
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__': unittest.main()
