# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No Kit/device: authenticated Bridge lease rotation and failure receipts."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


def bridge_class():
    package = ModuleType('_tp_bridge_lease_test')
    package.__path__ = []
    adapter = ModuleType('_tp_bridge_lease_test.isaac_adapter')
    adapter.IsaacSimulationAdapter = object
    path = Path(__file__).resolve().parents[2] / 'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py'
    spec = importlib.util.spec_from_file_location('_tp_bridge_lease_test.bridge_client', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {package.__name__: package, adapter.__name__: adapter}):
        spec.loader.exec_module(module)
    return module.BridgeClient


BridgeClient = bridge_class()


class BridgeLeaseRotationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = SimpleNamespace(stage_epoch='stage', engine_session_id='engine')
        self.client = BridgeClient(self.adapter, base_url='http://127.0.0.1:1',
                                   bootstrap_secret='x' * 32, clock=lambda: 10.)
        self.client._lease_id = 'old'
        self.client._lease_valid = True
        self.command = SimpleNamespace(control_lease_id='new',command_id='fixture-command')

    def test_rotated_command_refreshes_authenticated_grant_before_queue(self):
        def post(path, body):
            self.assertEqual(path, '/v1/engine/heartbeat')
            self.assertEqual(body, {'engine_session_id': 'engine', 'stage_epoch': 'stage'})
            self.assertFalse(self.client._lease_valid)
            self.assertIsNone(self.client._lease_id)
            self.assertEqual(list(self.client._incoming), [])
            return {'lease_valid': True, 'control_lease_id': 'new'}
        self.client._post = post
        self.client._queue_claimed_command(self.command, 'stage')
        self.assertTrue(self.client._lease_valid)
        self.assertEqual(self.client._lease_id, 'new')
        self.assertEqual(list(self.client._incoming), [self.command])

    def test_same_current_grant_does_not_add_network_roundtrip(self):
        self.client._post = lambda *a, **k: self.fail('Unexpected heartbeat')
        self.command.control_lease_id = 'old'
        self.client._queue_claimed_command(self.command, 'stage')
        self.assertTrue(self.client._lease_valid)
        self.assertEqual(self.client._lease_id, 'old')

    def test_command_cannot_grant_itself_on_mismatch_or_expiry(self):
        for response in ({'lease_valid': True, 'control_lease_id': 'other'},
                         {'lease_valid': False, 'control_lease_id': None},
                         {'lease_valid': True, 'control_lease_id': None}):
            with self.subTest(response=response):
                self.setUp()
                self.client._post = lambda *a: response
                self.client._queue_claimed_command(self.command, 'stage')
                self.assertNotEqual(self.client._lease_id, self.command.control_lease_id)
                if response['control_lease_id'] is None:
                    self.assertFalse(self.client._lease_valid)
                self.assertEqual(list(self.client._incoming), [self.command])

    def test_failed_refresh_preserves_claim_for_rejection_without_authority(self):
        def fail(*a): raise OSError('offline-test-transport-failed')
        self.client._post = fail
        with self.assertRaisesRegex(OSError, 'offline-test-transport-failed'):
            self.client._queue_claimed_command(self.command, 'stage')
        self.assertFalse(self.client._lease_valid)
        self.assertIsNone(self.client._lease_id)
        self.assertEqual(list(self.client._incoming), [self.command])

    def test_main_thread_applies_refreshed_grant_before_execute(self):
        events = []
        self.client._post = lambda *a: {'lease_valid': True, 'control_lease_id': 'new'}
        self.client._queue_claimed_command(self.command, 'stage')
        self.adapter.refresh_stage_epoch = lambda: False
        self.adapter.update_control_lease = lambda lease, valid: events.append(('lease', lease, valid))
        self.adapter.runtime = SimpleNamespace(state='paused')
        self.adapter.execute = lambda command: events.append(('execute', command.control_lease_id))
        self.adapter.snapshot = lambda: None
        self.client.update()
        self.assertEqual(events, [('lease', 'new', True), ('execute', 'new')])

    def test_watchdog_still_invalidates_refreshed_grant_before_execute(self):
        events = []
        self.client._post = lambda *a: {'lease_valid': True, 'control_lease_id': 'new'}
        self.client._queue_claimed_command(self.command, 'stage')
        self.client._last_success = 0.
        self.adapter.refresh_stage_epoch = lambda: False
        self.adapter.update_control_lease = lambda lease, valid: events.append(('lease', lease, valid))
        self.adapter.runtime = SimpleNamespace(state='paused')
        self.adapter.fail_safe_pause = lambda reason: events.append(('pause', reason))
        self.adapter.execute = lambda command: events.append(('execute', command.control_lease_id))
        self.adapter.snapshot = lambda: None
        self.client.update()
        self.assertEqual(events[0], ('lease', 'new', False))
        self.assertEqual(events[1], ('pause', 'Backend connection lost'))
