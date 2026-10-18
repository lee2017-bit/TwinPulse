# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline pool/admission tests. No SSH, robot process, sensor or motor starts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))

from twinpulse_app.command_broker import BrokerError
from twinpulse_app.physical_fleet_adapter import PhysicalFleetAdapter, PhysicalFleetServices
from twinpulse_app.robot_adapters import instance_binding, ADAPTER_ID


class Service:
    def __init__(self, name, trace):
        self.name, self.trace = name, trace
        self.binding = None
        self.bindings = []
        self.closed = False
        self.close_error = False
        self.active_after_close = False

    def bind_instance(self, binding):
        self.bindings.append(deepcopy(binding))
        self.binding = deepcopy(binding)

    def close(self):
        self.trace.append((self.name, 'close'))
        if self.close_error:
            raise OSError('synthetic close failure')
        self.closed = True


class Diagnostics(Service):
    def __init__(self, name, trace):
        super().__init__(name, trace)
        self.token = 'SYNTHETIC_TOKEN_MUST_NOT_BE_PERSISTED'
        self.job, self.record = None, None
        self.preflights = self.starts = 0
        self.fail_start = False
        self.identity = Path('unused-key-path')
        self.known_hosts = Path('unused-known-hosts-path')

    def preflight(self, owner):
        self.preflights += 1
        return {'start_token': self.token}

    def start(self, owner, token, confirmed):
        assert token == self.token and confirmed is True
        self.starts += 1
        if self.fail_start:
            raise OSError('synthetic uncertain transport failure')
        self.job = {'id': uuid4().hex[:24], 'execution_id': uuid4().hex,
                    'robot_binding': deepcopy(self.binding), 'status': 'RUNNING',
                    'authentication_verified': False}
        return self.snapshot(owner)

    def snapshot(self, owner):
        return {'robot_binding': deepcopy(self.binding), 'job': deepcopy(self.job),
                'record': deepcopy(self.record)}

    def _running(self):
        return bool(self.job and self.job['status'] == 'RUNNING'
                    and (not self.closed or self.active_after_close))

    def complete(self):
        self.job.update(status='COMPLETED', authentication_verified=True)
        self.record = {'age_seconds': 2, 'battery': {'voltage_v': 11.8},
                       'boot_id': 'synthetic-boot', 'release_id': 'synthetic-release'}


class Readiness(Service):
    active = False

    def blocks_read_only_observation(self):
        return self.local_operation_active()

    def local_operation_active(self):
        return self.active and (not self.closed or self.active_after_close)

    def snapshot(self, owner):
        return {'robot_binding': self.binding}


class Controller(Service):
    def __init__(self, name, trace):
        super().__init__(name, trace)
        self.busy, self.owner, self.mode = False, None, 'control_scan'
        self.job, self.sequence = uuid4().hex, 0
        self.inputs = []
        self.input_error = False

    def snapshot(self, owner):
        return {'robot_binding': self.binding, 'selected_robot_binding': self.binding,
                'owned': self.owner == owner, 'job_id': self.job if self.owner == owner else None,
                'sequence': self.sequence, 'mode': self.mode, 'state': 'READY',
                'busy': self.busy and (not self.closed or self.active_after_close)}

    def input(self, owner, job, sequence, action, expires):
        self.trace.append((self.name, 'input', action))
        self.inputs.append((owner, job, sequence, action, expires))
        self.sequence = sequence
        if self.input_error:
            raise OSError('synthetic input failure')

    def start(self, *args, **kwargs):
        raise AssertionError('Hardware start is forbidden in this test')


class PhysicalFleetAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.trace, self.created = [], {}
        self.rows = [self.row('Robot A', '192.0.2.1'), self.row('Robot B', '192.0.2.2')]
        self.registry = SimpleNamespace(snapshot=lambda: {'robots': deepcopy(self.rows)})
        self.devices = SimpleNamespace(
            registry_service=SimpleNamespace(registry=self.registry), lock=RLock(), closed=False,
            diagnostics=Diagnostics('legacy-diagnostics', self.trace),
            readiness=Readiness('legacy-readiness', self.trace),
            controller=Controller('legacy-controller', self.trace), contexts=[])
        self.pool = PhysicalFleetAdapter(self.devices, ROOT, self.tmp.name, services_factory=self.factory)
        self.addCleanup(self.pool.close)
        self.owner = 'SYNTHETIC_OWNER_MUST_NOT_BE_PERSISTED'

    @staticmethod
    def row(label, host):
        return {'id': uuid4().hex, 'label': label, 'adapter_id': ADAPTER_ID,
                'endpoint': {'host': host, 'user': 'twinpulse', 'port': 22, 'ros_domain_id': 86}}

    def factory(self, binding, archive):
        rid = binding['instance_id']
        result = PhysicalFleetServices(Diagnostics(rid + '/diag', self.trace),
            Readiness(rid + '/ready', self.trace), Controller(rid + '/controller', self.trace))
        self.created[rid] = result
        return result

    def connect(self, index=0, **overrides):
        values = dict(request_id=uuid4().hex, operation_id=uuid4().hex, project_id='project-a')
        values.update(overrides)
        return self.pool.check_connection(self.rows[index]['id'], self.owner, **values)

    def active(self, index=0, mode='control_scan'):
        service = self.created[self.rows[index]['id']].controller
        service.busy, service.owner, service.mode = True, self.owner, mode
        return service

    def assert_code(self, code, callback):
        with self.assertRaises(BrokerError) as result:
            callback()
        self.assertEqual(result.exception.code, code)

    def test_lazy_snapshot_and_focus_do_not_create_services(self):
        self.assertEqual(self.pool.snapshot(self.owner)['robots'], [])
        self.pool.focus(self.rows[0]['id'], self.owner)
        self.pool.focus(self.rows[1]['id'], self.owner)
        self.assertFalse(self.created)
        self.assertFalse(self.trace)

    def test_two_services_remain_bound_once_and_other_robot_can_connect(self):
        a = self.connect(0)
        b = self.connect(1)  # A's diagnostic remains running; B is independent.
        self.assertNotEqual(a['connection_epoch'], b['connection_epoch'])
        self.pool.focus(self.rows[0]['id'], self.owner)
        self.pool.focus(self.rows[1]['id'], self.owner)
        for services in self.created.values():
            for service in (services.diagnostics, services.readiness, services.controller):
                self.assertEqual(len(service.bindings), 1)
                self.assertFalse(service.closed)
        self.assertEqual(len(self.pool.snapshot(self.owner)['robots']), 2)

    def test_focus_releases_manual_only_and_retains_all_services(self):
        self.connect()
        old = self.pool.snapshot(self.owner)['robots'][0]['motion_epoch']
        controller = self.active()
        self.pool.focus(self.rows[0]['id'], self.owner)
        self.pool.focus(self.rows[1]['id'], self.owner)
        self.assertEqual([x[3] for x in controller.inputs], ['stop'])
        self.assertFalse(controller.closed)
        self.assertTrue(self.created[self.rows[0]['id']].diagnostics._running())
        self.assertNotEqual(self.pool.snapshot(self.owner)['robots'][0]['motion_epoch'], old)

    def test_sensor_only_focus_and_stop_do_not_cancel_collection(self):
        self.connect()
        controller = self.active(mode='lidar')
        self.pool.focus(self.rows[0]['id'], self.owner)
        self.pool.focus(self.rows[1]['id'], self.owner)
        self.pool.stop(self.rows[0]['id'], self.owner)
        self.assertFalse(controller.inputs)
        self.assertFalse(controller.closed)

    def test_request_replay_starts_once_changed_contents_rejected(self):
        request, operation = uuid4().hex, uuid4().hex
        first = self.connect(request_id=request, operation_id=operation)
        second = self.connect(request_id=request, operation_id=operation)
        self.assertEqual(first['connection_epoch'], second['connection_epoch'])
        diag = self.created[self.rows[0]['id']].diagnostics
        self.assertEqual((diag.preflights, diag.starts), (1, 1))
        self.assert_code('physical_fleet_request_reused', lambda: self.connect(request_id=request))

    def test_preflight_and_uncertain_failure_replay_do_not_restart(self):
        self.pool._entry(self.rows[0]['id'], create=True)
        diag = self.created[self.rows[0]['id']].diagnostics
        diag.token = None
        request, operation = uuid4().hex, uuid4().hex
        for _ in range(2):
            self.assert_code('robot_preflight_required', lambda: self.connect(request_id=request, operation_id=operation))
        self.assertEqual((diag.preflights, diag.starts), (1, 0))
        diag.token, diag.fail_start = 'synthetic-token', True
        request = uuid4().hex
        for _ in range(2):
            self.assert_code('physical_fleet_check_failed', lambda: self.connect(request_id=request, operation_id=operation))
        self.assertEqual((diag.preflights, diag.starts), (2, 1))

    def test_read_only_completed_snapshot_never_claims_live_connection(self):
        self.connect()
        diag = self.created[self.rows[0]['id']].diagnostics
        diag.complete()
        value = self.pool.snapshot(self.owner)['robots'][0]
        self.assertEqual(value['connection_state'], 'DEGRADED')
        self.assertEqual(value['observation_state'], 'VERIFIED_SNAPSHOT')
        self.assertFalse(value['live_heartbeat'])
        self.assertIsNone(value['battery']['voltage_v'])
        self.assertEqual(value['last_observation']['battery']['voltage_v'], 11.8)
        diag.job['robot_binding']['sha256'] = 'wrong'
        self.assertIsNone(self.pool.snapshot(self.owner)['robots'][0]['last_observation'])

    def test_nonfinite_stale_age_and_failed_job_are_not_fresh(self):
        self.connect()
        diag = self.created[self.rows[0]['id']].diagnostics
        diag.complete()
        for age in (float('nan'), float('inf'), -1, 121, True, None):
            diag.record['age_seconds'] = age
            value = self.pool.snapshot(self.owner)['robots'][0]
            self.assertEqual(value['observation_state'], 'STALE_OR_UNVERIFIED')
            self.assertIsNone(value['telemetry_age_ms'])
        diag.record['age_seconds'] = 0
        diag.job['status'] = 'FAILED'
        self.assertIsNone(self.pool.snapshot(self.owner)['robots'][0]['last_observation'])

    def test_guard_unavailable_never_starts_controller_or_lidar(self):
        self.connect()
        rid = self.rows[0]['id']
        for method in (self.pool.prepare_control, self.pool.drive):
            self.assert_code('physical_protective_guards_unavailable', lambda: method(rid, self.owner))
        self.assert_code('physical_native_lidar_unavailable', lambda: self.pool.lidar(rid, self.owner, enabled=True))
        value = self.pool.snapshot(self.owner)['robots'][0]
        self.assertFalse(value['capabilities']['drive'])
        self.assertFalse(value['capabilities']['lidar'])
        self.assertIn('PHYSICAL_NONUNIFORM_NATIVE_SCAN_ADAPTER_NOT_INTEGRATED', value['blockers'])
        self.assertFalse(self.trace)

    def test_foreign_owner_cannot_stop_disconnect_or_inspect_operation(self):
        result = self.connect()
        controller = self.active()
        rid = self.rows[0]['id']
        for call in (lambda: self.pool.stop(rid, 'other'), lambda: self.pool.disconnect(rid, 'other'),
                     lambda: self.pool.operation(result['operation_id'], 'other')):
            self.assert_code('physical_fleet_owned', call)
        self.assertFalse(controller.inputs)
        self.assertFalse(controller.closed)

    def test_same_endpoint_different_user_or_domain_cannot_duplicate_owner(self):
        self.connect()
        self.rows[1]['endpoint'].update(host='192.0.2.1', user='different', ros_domain_id=10)
        self.assert_code('physical_fleet_endpoint_owned', lambda: self.connect(1))
        self.assertEqual(len(self.created), 1)

    def test_binding_change_blocks_check_but_stop_and_disconnect_still_work(self):
        self.connect()
        controller = self.active()
        rid = self.rows[0]['id']
        self.rows[0]['endpoint']['host'] = '192.0.2.99'
        self.assert_code('physical_fleet_binding_changed', self.connect)
        self.rows.clear()  # Even deleted metadata cannot suppress the old Stop.
        self.pool.stop(rid, self.owner)
        self.pool.disconnect(rid, self.owner)
        self.assertEqual([x[3] for x in controller.inputs], ['stop', 'close'])
        self.assertTrue(controller.closed)

    def test_legacy_busy_same_endpoint_and_scene_change_block(self):
        self.devices.controller.bind_instance(instance_binding(self.rows[0]))
        self.devices.controller.busy = True
        self.assert_code('physical_fleet_legacy_busy', self.connect)
        self.assertEqual(self.created[self.rows[0]['id']].diagnostics.starts, 0)
        self.devices.controller.busy = False
        self.devices.contexts = [SimpleNamespace(workspace=SimpleNamespace(switching=lambda: True))]
        self.assert_code('project_switch_pending', self.connect)

    def test_readiness_target_blocks_without_affecting_other_robot(self):
        self.pool._entry(self.rows[0]['id'], create=True)
        self.created[self.rows[0]['id']].readiness.active = True
        self.assert_code('readiness_busy_or_uncertain', self.connect)
        self.connect(1)

    def test_disabled_backend_and_unreviewed_adapter_do_not_create_pool(self):
        self.devices.diagnostics = None
        self.assert_code('robot_diagnostics_unavailable', self.connect)
        self.devices.diagnostics = Diagnostics('legacy-diagnostics', self.trace)
        self.rows[0]['adapter_id'] = 'unreviewed'
        self.assert_code('robot_adapter_unreviewed', self.connect)
        self.assertFalse(self.created)

    def test_manifest_links_existing_job_and_never_persists_owner_or_token(self):
        value = self.connect()
        self.pool.disconnect(self.rows[0]['id'], self.owner)
        operation = self.pool.operation(value['operation_id'], self.owner)
        self.assertTrue(operation['manifest']['complete'])
        self.assertFalse(operation['manifest']['physical_motion_verified'])
        self.assertEqual(operation['project_id'], 'project-a')
        event = next(e for e in operation['events'] if e['kind'] == 'read_only_job_bound')
        self.assertEqual(event['data']['job_id'], value['diagnostic_job_id'])
        self.assertTrue(event['data']['execution_id'])
        saved = Path(self.tmp.name, operation['manifest']['persistent_manifest']).read_text()
        self.assertNotIn(self.owner, saved)
        self.assertNotIn('SYNTHETIC_TOKEN', saved)
        rows = [json.loads(line) for line in saved.splitlines()]
        self.assertEqual(rows[:-1], operation['events'])
        self.assertEqual(rows[-1]['schema_version'], 'physical-fleet-footer-1.0')
        self.assertEqual(rows[-1]['event_count'], len(operation['events']))
        raw = Path(self.tmp.name, operation['manifest']['persistent_manifest']).read_bytes()
        self.assertEqual(rows[-1]['events_sha256'], hashlib.sha256(b''.join(raw.splitlines(keepends=True)[:-1])).hexdigest())

    def test_event_capacity_and_journal_failure_never_prevent_stop(self):
        value = self.connect()
        controller = self.active()
        entry = self.pool.sessions[self.rows[0]['id']]
        with patch.object(entry.journal, 'append', return_value=False):
            for _ in range(270):
                self.pool.stop(self.rows[0]['id'], self.owner)
        self.assertEqual(len(controller.inputs), 270)
        self.assertLessEqual(len(entry.events), 256)
        self.assertGreater(entry.dropped_events, 0)
        self.assertFalse(self.pool.operation(value['operation_id'], self.owner)['manifest']['complete'])

    def test_reconnect_has_fresh_epoch_keeps_prior_operation_evidence(self):
        request = uuid4().hex
        first = self.connect(request_id=request)
        services = self.created[self.rows[0]['id']]
        self.pool.disconnect(self.rows[0]['id'], self.owner)
        self.assertTrue(self.pool.snapshot(self.owner)['robots'][0]['capabilities']['read_only_connection'])
        second = self.connect()
        replacement = self.created[self.rows[0]['id']]
        self.assertIsNot(services, replacement)
        self.assertTrue(services.diagnostics.closed)
        self.assertFalse(replacement.diagnostics.closed)
        self.assertEqual(replacement.diagnostics.starts, 1)
        self.assertNotEqual(first['operation_id'], second['operation_id'])
        self.assertNotEqual(first['connection_epoch'], second['connection_epoch'])
        self.assertNotEqual(first['motion_epoch'], second['motion_epoch'])
        self.assert_code('physical_fleet_request_reused', lambda: self.connect(request_id=request, operation_id=first['operation_id']))
        self.assertEqual(replacement.diagnostics.starts, 1)
        self.assertTrue(self.pool.operation(first['operation_id'], self.owner)['manifest']['complete'])
        self.assertFalse(self.pool.operation(second['operation_id'], self.owner)['manifest']['complete'])

    def history_session(self, *, owner=None, project='project-a', role='product', expired=False):
        # Use the actual API session validator without starting a server.
        from twinpulse_app.api import LocalApiServer, _Session
        owner = self.owner if owner is None else owner
        context = SimpleNamespace(broker=SimpleNamespace(project_id=project), _session_lock=RLock(),
            _clock=lambda: 10., _session_idle_ttl_s=30.,
            _sessions={owner: _Session(owner, role, None, 5. if expired else 40., 50.)})
        context._session = lambda identity, required_role: LocalApiServer._session(context, identity, required_role)
        self.devices.contexts = [context]
        return context

    def saved_operation(self):
        value = self.connect()
        self.pool.disconnect(self.rows[0]['id'], self.owner)
        identity = value['operation_id']
        path = Path(self.tmp.name, 'physical-fleet-operations', identity + '.jsonl')
        return identity, path, path.read_bytes()

    def cold_pool(self):
        def forbidden(*args):
            raise AssertionError('Cold history must never construct physical services')
        pool = PhysicalFleetAdapter(self.devices, ROOT, self.tmp.name, services_factory=forbidden)
        self.addCleanup(pool.close)
        return pool

    def test_cold_history_authenticates_current_project_without_restoring_authority(self):
        identity, path, original = self.saved_operation()
        # A valid new product session may read same-project history, but is NOT
        # presented as authenticated identity of the historical operator.
        new_owner = 'SYNTHETIC_NEW_PRODUCT_SESSION'
        self.history_session(owner=new_owner)
        cold = self.cold_pool()
        with patch('subprocess.Popen', side_effect=AssertionError('NO_TRANSPORT')):
            result = cold.operation(identity, new_owner, project_id='project-a')
        self.assertTrue(result['manifest']['complete'])
        self.assertEqual(result['manifest']['completeness'], 'VERIFIED_CLOSED_RECORDING')
        self.assertFalse(result['manifest']['historical_operator_identity_verified'])
        self.assertFalse(result['manifest']['connection_restored'])
        self.assertFalse(result['manifest']['device_authority_restored'])
        self.assertEqual(result['robot_id'], self.rows[0]['id'])
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(cold.sessions)
        self.assertFalse(cold.operations)
        self.assertFalse(cold.requests)
        self.assertNotIn(new_owner.encode(), original)
        self.assertNotIn(self.owner.encode(), original)

    def test_cold_history_missing_invalid_expired_role_or_project_session_denied_before_io(self):
        identity, _, _ = self.saved_operation()
        cold = self.cold_pool()
        for kind in ('absent', 'wrong-owner', 'expired', 'wrong-role', 'wrong-project', 'flag-not-session'):
            with self.subTest(kind=kind):
                context = self.history_session(expired=kind == 'expired',
                    role='engine' if kind == 'wrong-role' else 'product',
                    project='project-b' if kind == 'wrong-project' else 'project-a')
                if kind == 'absent':
                    self.devices.contexts = []
                if kind == 'flag-not-session':
                    context._session = lambda *_: True
                with patch.object(Path, 'open', side_effect=AssertionError('Unauthenticated history read')):
                    self.assert_code('physical_fleet_history_auth_required', lambda: cold.operation(
                        identity, 'unknown-owner' if kind == 'wrong-owner' else self.owner, project_id='project-a'))
        self.history_session()
        self.assert_code('physical_fleet_history_auth_required', lambda: cold.operation(identity, self.owner))

    def test_cold_history_project_robot_and_current_binding_must_match(self):
        identity, path, original = self.saved_operation()
        cold = self.cold_pool()
        self.history_session(project='project-b')
        self.assert_code('physical_fleet_history_binding_unverified', lambda: cold.operation(identity, self.owner, project_id='project-b'))
        self.history_session()
        self.rows[0]['endpoint']['host'] = '192.0.2.99'
        self.assert_code('physical_fleet_history_binding_unverified', lambda: cold.operation(identity, self.owner, project_id='project-a'))
        self.rows.clear()
        self.assert_code('physical_fleet_history_binding_unverified', lambda: cold.operation(identity, self.owner, project_id='project-a'))
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(cold.sessions)

    def test_cold_legacy_or_truncated_footer_preserves_prefix_as_incomplete(self):
        identity, path, original = self.saved_operation()
        self.history_session()
        cold = self.cold_pool()
        lines = original.splitlines(keepends=True)
        for payload in (b''.join(lines[:-1]), b''.join(lines[:-1]) + lines[-1][:40], original.rstrip(b'\n')):
            with self.subTest(last_bytes=payload[-10:]):
                path.write_bytes(payload)
                result = cold.operation(identity, self.owner, project_id='project-a')
                self.assertFalse(result['manifest']['complete'])
                self.assertEqual(result['manifest']['completeness'], 'RECOVERED_INCOMPLETE')
                self.assertEqual(len(result['events']), len(lines)-1)
                self.assertEqual(path.read_bytes(), payload)

    def test_cold_corrupt_sequence_or_foreign_event_is_not_exposed(self):
        identity, path, original = self.saved_operation()
        self.history_session()
        cold = self.cold_pool()
        lines = original.splitlines(keepends=True)
        for field, value in (('sequence', 99), ('robot_id', self.rows[1]['id']),
                             ('project_id', 'project-b'), ('data', {'secret': 'MUST_NOT_LEAK'})):
            with self.subTest(field=field):
                event = json.loads(lines[1])
                event[field] = value
                payload = lines[0] + json.dumps(event).encode() + b'\n' + b''.join(lines[2:])
                path.write_bytes(payload)
                result = cold.operation(identity, self.owner, project_id='project-a')
                self.assertFalse(result['manifest']['complete'])
                self.assertEqual(len(result['events']), 1)
                self.assertNotIn('MUST_NOT_LEAK', json.dumps(result))
                self.assertIn('JOURNAL_CORRUPT_OR_SEQUENCE_GAP', result['manifest']['missing'])
                self.assertEqual(path.read_bytes(), payload)

    def test_cold_footer_count_hash_drops_and_trailing_data_are_incomplete(self):
        identity, path, original = self.saved_operation()
        self.history_session()
        cold = self.cold_pool()
        lines = original.splitlines(keepends=True)
        for field, value in (('event_count', 999), ('events_sha256', '0'*64), ('complete', False), ('dropped_events', 1)):
            with self.subTest(field=field):
                footer = json.loads(lines[-1])
                footer[field] = value
                payload = b''.join(lines[:-1]) + json.dumps(footer).encode() + b'\n'
                path.write_bytes(payload)
                self.assertFalse(cold.operation(identity, self.owner, project_id='project-a')['manifest']['complete'])
                self.assertEqual(path.read_bytes(), payload)
        path.write_bytes(original + lines[0])
        result = cold.operation(identity, self.owner, project_id='project-a')
        self.assertIn('DATA_AFTER_FOOTER', result['manifest']['missing'])
        self.assertFalse(result['manifest']['complete'])

    def test_cold_unverifiable_header_missing_file_and_oversized_file_do_not_leak(self):
        identity, path, original = self.saved_operation()
        self.history_session()
        cold = self.cold_pool()
        first = json.loads(original.splitlines()[0])
        malformed_data = deepcopy(first)
        malformed_data['data'] = []
        for payload in (b'', b'{broken', b'\xff\n', json.dumps(malformed_data).encode() + b'\n',
                        b'{"project_id":"project-a","project_id":"project-b"}\n'):
            with self.subTest(header=payload[:20]):
                path.write_bytes(payload)
                self.assert_code('physical_fleet_history_binding_unverified', lambda: cold.operation(identity, self.owner, project_id='project-a'))
        path.write_bytes(b'x' * (1024*1024+4097))
        self.assert_code('physical_fleet_history_capacity', lambda: cold.operation(identity, self.owner, project_id='project-a'))
        self.assert_code('physical_fleet_operation_missing', lambda: cold.operation(uuid4().hex, self.owner, project_id='project-a'))

    def test_failed_footer_sync_marks_warm_recording_incomplete(self):
        value = self.connect()
        with patch('twinpulse_app.physical_fleet_adapter.os.fsync', side_effect=OSError('synthetic footer sync failure')):
            self.pool.disconnect(self.rows[0]['id'], self.owner)
        manifest = self.pool.operation(value['operation_id'], self.owner)['manifest']
        self.assertFalse(manifest['complete'])
        self.assertEqual(manifest['footer_error'], 'FINAL_RECORDING_RECEIPT_WRITE_FAILED')
        self.assertEqual(self.pool.snapshot(self.owner)['robots'][0]['recording_state'], 'INCOMPLETE')

    def test_warm_operation_project_filter_rejects_other_project(self):
        value = self.connect()
        self.assert_code('physical_fleet_operation_project', lambda: self.pool.operation(value['operation_id'], self.owner, project_id='project-b'))

    def test_reconnect_rejects_old_operation_id_warm_and_cold_without_overwrite(self):
        identity, path, original = self.saved_operation()
        self.assert_code('physical_fleet_operation_reused', lambda: self.connect(operation_id=identity))
        self.assertEqual(self.created[self.rows[0]['id']].diagnostics.starts, 0)
        # A new adapter lifetime also rejects an existing evidence filename
        # before any preflight/transport; only a new explicit ID may reconnect.
        pool = PhysicalFleetAdapter(self.devices, ROOT, self.tmp.name, services_factory=self.factory)
        self.addCleanup(pool.close)
        self.assert_code('physical_fleet_operation_reused', lambda: pool.check_connection(
            self.rows[0]['id'], self.owner, request_id=uuid4().hex, operation_id=identity, project_id='project-a'))
        self.assertEqual(self.created[self.rows[0]['id']].diagnostics.starts, 0)
        new = pool.check_connection(self.rows[0]['id'], self.owner, request_id=uuid4().hex,
                                   operation_id=uuid4().hex, project_id='project-a')
        self.assertNotEqual(new['operation_id'], identity)
        self.assertEqual(self.created[self.rows[0]['id']].diagnostics.starts, 1)
        self.assertEqual(path.read_bytes(), original)

    def test_stop_after_disconnect_is_idempotent_and_keeps_manifest_complete(self):
        value = self.connect()
        rid = self.rows[0]['id']
        self.pool.disconnect(rid, self.owner)
        before = self.pool.operation(value['operation_id'], self.owner)
        self.pool.stop(rid, self.owner)
        self.assertEqual(self.pool.operation(value['operation_id'], self.owner), before)

    def test_foreign_focus_never_rotates_or_stops_owned_robot(self):
        self.connect()
        controller = self.active(mode='lidar')
        before = self.pool.snapshot(self.owner)['robots'][0]['motion_epoch']
        self.pool.focus(self.rows[0]['id'], 'other')
        self.pool.focus(self.rows[1]['id'], 'other')
        self.assertEqual(self.pool.snapshot(self.owner)['robots'][0]['motion_epoch'], before)
        self.assertFalse(controller.inputs)

    def test_reciprocal_legacy_and_scene_admission_checks_pool(self):
        self.connect()
        self.assert_code('physical_fleet_busy', self.pool.assert_legacy_available)
        self.assert_code('physical_fleet_busy', lambda: self.pool.assert_legacy_available(instance_binding(self.rows[0])))
        self.pool.assert_legacy_available(instance_binding(self.rows[1]))
        self.created[self.rows[0]['id']].diagnostics.complete()
        self.pool.assert_legacy_available()

    def test_close_stops_every_robot_before_joining_any_service(self):
        self.connect(0)
        self.connect(1)
        self.active(0)
        self.active(1)
        self.pool.close()
        first_close = next(i for i, event in enumerate(self.trace) if event[1] == 'close')
        self.assertEqual([event[2] for event in self.trace[:first_close]], ['close', 'close'])

    def test_failed_stop_still_closes_and_uncertain_cleanup_retains_reservation(self):
        self.connect()
        controller = self.active()
        controller.input_error, controller.active_after_close = True, True
        self.pool.disconnect(self.rows[0]['id'], self.owner)
        self.assertTrue(controller.closed)
        value = self.pool.snapshot(self.owner)['robots'][0]
        self.assertEqual(value['control_state'], 'FAULT')
        self.assertNotEqual(value['connection_state'], 'DISCONNECTED')
        self.assert_code('physical_fleet_cleanup_uncertain', self.connect)
        self.rows[1]['endpoint'] = deepcopy(self.rows[0]['endpoint'])
        self.assert_code('physical_fleet_endpoint_owned', lambda: self.connect(1))

    def test_real_service_constructor_is_offline_and_binds_once(self):
        # Default factory only constructs existing classes. Prevent accidental
        # transport even if a future constructor regresses.
        pool = PhysicalFleetAdapter(self.devices, ROOT, Path(self.tmp.name) / 'real-services')
        self.addCleanup(pool.close)
        with patch('subprocess.Popen', side_effect=AssertionError('NO_TRANSPORT')):
            entry = pool._entry(self.rows[0]['id'], create=True)
            value = pool.snapshot(self.owner)['robots'][0]
            self.assertEqual(value['connection_state'], 'DEGRADED')
            self.assertEqual(entry.services.controller.snapshot(None)['selected_robot_binding'], entry.binding)
            self.assertFalse(entry.services.diagnostics._running())


if __name__ == '__main__':
    unittest.main()
