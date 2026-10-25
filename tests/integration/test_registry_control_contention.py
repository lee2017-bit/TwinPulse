# SPDX-License-Identifier: Apache-2.0
"""Real local registry + public fleet action boundary; no transport or motors."""
from copy import deepcopy
from threading import Event, Thread
from unittest.mock import patch
from uuid import uuid4
import unittest

from tests.integration import test_physical_live_session as live_fixtures
from twinpulse_app.robot_registry import RobotRegistry, RobotEndpoint
from twinpulse_app.robot_adapters import instance_binding, ADAPTER_VERSION
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.robot_battery import battery_display_config, battery_display_sha256


class RegistryControlContentionTests(unittest.TestCase):
    action=live_fixtures.FleetPhysicalEnvelopeTests.action

    def setUp(self):
        live_fixtures.FleetPhysicalEnvelopeTests.setUp(self)
        self.registry=RobotRegistry(self.tmp.name+'/actual-registry')
        self.row=self.registry.register(label='Real registry fixture',adapter_id=self.row['adapter_id'],
            endpoint=RobotEndpoint('192.0.2.1','twinpulse'),expected_revision=0,adapter_version=ADAPTER_VERSION)
        self.identity=self.row['id']
        self.devices.registry_service.registry=self.registry
        self.pool.registry=self.registry
        self.input_sequence=0

    def _connect(self):
        self.action('focus');self.action('connect')

    def _send(self, action):
        row=self.fleet.robots[self.identity]
        self.input_sequence+=1
        payload=dict(direction='forward',sequence=self.input_sequence,expires_at_ms=100250) if action=='drive' else {}
        return self.fleet.action(dict(action=action,request_id=uuid4().hex,robot_id=self.identity,
            connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],payload=payload),self.owner)

    def test_blocked_battery_and_timing_refresh_do_not_delay_drive_stop_or_response(self):
        self._connect()
        for attribute,obj in [('_battery_config',self.registry),('read',self.registry.timing_store)]:
            with self.subTest(attribute=attribute):
                entered,release=Event(),Event();errors=[]
                original=getattr(obj,attribute)
                def block(*args,**kwargs):
                    entered.set()
                    if not release.wait(3):raise RuntimeError('TEST_SIDECAR_BARRIER_TIMEOUT')
                    return original(*args,**kwargs)
                def refresh():
                    try:self.registry.snapshot()
                    except BaseException as error:errors.append(error)
                with patch.object(obj,attribute,side_effect=block):
                    thread=Thread(target=refresh);thread.start()
                    try:
                        self.assertTrue(entered.wait(1))
                        self.assertEqual(self.registry.registered(self.identity)['id'],self.identity)
                        self._send('drive');self._send('stop')
                        self.assertFalse(release.is_set())
                        self.assertEqual([row[0] for row in self.trace[-2:]],['drive','stop'])
                    finally:release.set();thread.join(4)
                self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    def test_disconnected_robot_saved_settings_get_does_not_hold_fleet_mutex(self):
        self._connect()
        other=self.registry.register(label='Disconnected other robot',adapter_id=self.row['adapter_id'],
            endpoint=RobotEndpoint('192.0.2.2','twinpulse'),expected_revision=1,adapter_version=ADAPTER_VERSION)
        entered,release=Event(),Event();errors=[]
        original=self.pool.profile_for_view
        def read(identity):
            if identity==other['id']:
                entered.set()
                if not release.wait(3):raise RuntimeError('TEST_SAVED_VIEW_BARRIER_TIMEOUT')
            return original(identity)
        def refresh():
            try:self.fleet.snapshot()
            except BaseException as error:errors.append(error)
        with patch.object(self.pool,'profile_for_view',side_effect=read):
            thread=Thread(target=refresh);thread.start()
            try:
                self.assertTrue(entered.wait(1))
                with patch.object(self.pool,'field_config_for_view',side_effect=AssertionError('control read optional field file')):
                    self._send('drive');self._send('stop')
                self.assertFalse(release.is_set())
            finally:release.set();thread.join(4)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    def test_cache_miss_is_voltage_only_and_explicit_settings_refresh_updates_it(self):
        self._connect()
        row=self.pool.snapshot()['robots'][0]
        self.assertIsNone(row['battery']['estimated_percent'])
        self.assertEqual(row['battery']['voltage_v'],11.8)
        self.assertEqual(row['battery']['age_ms'],62)
        self.assertEqual(row['battery']['display_settings_state'],'AWAITING_SETTINGS_VIEW')
        self.registry.snapshot()
        self.assertEqual(self.pool.snapshot()['robots'][0]['battery']['estimated_percent'],72.2)
        config=battery_display_config('custom');config['points']=[dict(voltage_v=10,percent=0),dict(voltage_v=12,percent=100)]
        self.registry.set_battery_display(self.identity,config,expected_revision=1,
            expected_display_sha256=battery_display_sha256(battery_display_config('robotis_opencr')))
        self.assertIsNone(self.pool.snapshot()['robots'][0]['battery']['estimated_percent'])
        self.registry.snapshot()
        with patch.object(self.registry,'snapshot',side_effect=AssertionError('control full registry read')):
            row=self._send('drive')['robots'][0]
        self.assertEqual(row['battery']['estimated_percent'],90)
        self.assertEqual(row['battery']['low_voltage_guard_v'],11.1)

    def test_connect_still_reads_actual_timing_profile_not_a_display_cache(self):
        binding=instance_binding(self.row)['sha256']
        expected=self.registry.timing_store.read(self.identity,binding)['profile']
        with patch.object(self.registry.timing_store,'read',wraps=self.registry.timing_store.read) as read:
            self._connect()
        read.assert_called_with(self.identity,binding)
        self.assertEqual(self.live.context['timing_profile'],expected)

    def test_changed_binding_and_removal_still_reject_drive_but_not_pinned_stop(self):
        self._connect()
        value=self.registry._read();value['robots'][0]['endpoint']['host']='192.0.2.99'
        with self.registry.lock:self.registry._publish(value,1)
        with self.assertRaisesRegex(BrokerError,'Disconnect the old instance'):self._send('drive')
        value=self.registry._read();value['robots']=[]
        with self.registry.lock:self.registry._publish(value,2)
        with self.assertRaisesRegex(BrokerError,'Registered robot not found'):self._send('drive')
        with patch.object(self.registry,'registration_snapshot',side_effect=AssertionError('Stop re-read registry')):
            self._send('stop')
        self.assertEqual(self.trace[-1][0],'stop')

    def test_live_battery_projection_does_not_acquire_registration_mutex(self):
        self._connect();self.registry.snapshot();done=Event();errors=[]
        def view():
            try:self.pool.snapshot()
            except BaseException as error:errors.append(error)
            finally:done.set()
        with self.registry.lock:
            thread=Thread(target=view);thread.start()
            self.assertTrue(done.wait(1),'entry->registry lock inversion')
        thread.join(2);self.assertEqual(errors,[])

    def test_late_refresh_cannot_republish_after_partial_settings_write_failure(self):
        original=self.registry._battery_config;entered,release=Event(),Event();errors=[]
        def block(row):
            config=original(row);entered.set()
            if not release.wait(3):raise RuntimeError('TEST_REFRESH_BARRIER_TIMEOUT')
            return config
        def refresh():
            try:self.registry.snapshot()
            except BaseException as error:errors.append(error)
        with patch.object(self.registry,'_battery_config',side_effect=block):
            thread=Thread(target=refresh);thread.start()
            try:
                self.assertTrue(entered.wait(1))
                with patch.object(self.registry,'_battery_config',side_effect=original),patch.object(self.registry,'_publish_locked',side_effect=OSError('synthetic CAS failure')):
                    with self.assertRaises(OSError):self.registry.set_battery_display(self.identity,battery_display_config(),expected_revision=1,
                        expected_display_sha256=battery_display_sha256(battery_display_config('robotis_opencr')))
            finally:release.set();thread.join(4)
        binding=instance_binding(self.row)['sha256']
        self.assertIsNone(self.registry.battery_display_for_view(self.identity,binding))
        self.assertEqual(errors,[])

    def test_older_refresh_cannot_overwrite_newer_external_partial_write_projection(self):
        original=self.registry._battery_config;entered,release=Event(),Event();errors=[]
        def read(row):
            value=original(row)
            if not entered.is_set():
                entered.set()
                if not release.wait(3):raise RuntimeError('TEST_EXTERNAL_REFRESH_BARRIER_TIMEOUT')
            return value
        def refresh():
            try:self.registry.snapshot()
            except BaseException as error:errors.append(error)
        with patch.object(self.registry,'_battery_config',side_effect=read):
            thread=Thread(target=refresh);thread.start()
            try:
                self.assertTrue(entered.wait(1))
                external=RobotRegistry(self.registry.path.parent)
                external._write_battery(self.identity,battery_display_config()) # Simulated external partial publish.
                self.registry.snapshot()
            finally:release.set();thread.join(4)
        binding=instance_binding(self.row)['sha256']
        self.assertEqual(self.registry.battery_display_for_view(self.identity,binding)['mode'],'voltage_only')
        self.assertEqual(errors,[])


if __name__=='__main__':unittest.main()
