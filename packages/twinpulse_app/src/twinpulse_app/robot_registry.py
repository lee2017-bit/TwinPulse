# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Robot instance registry, separate from discovery and supported adapters.

No constructor, list, register or select operation opens a device or connects
to a robot. Endpoint selections must be propagated through existing services
under the workspace device lock before this candidate becomes a product API.
"""
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4
from twinpulse_core.robot_battery import battery_display_config, checked_battery_display, battery_display_sha256


def record_battery_display(row):
    return checked_battery_display(row['battery_display']) if 'battery_display' in row else battery_display_config(
        'robotis_opencr' if row['adapter_id']=='turtlebot3_burger_v1' else 'voltage_only')


@dataclass(frozen=True)
class RobotEndpoint:
    host: str
    user: str
    port: int = 22
    ros_domain_id: int = 86

    def checked(self):
        if not isinstance(self.host, str) or not self.host or len(self.host) > 253:
            raise ValueError('ROBOT_HOST_INVALID')
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            if not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                       for part in self.host.split('.')):
                raise ValueError('ROBOT_HOST_INVALID') from None
        if not isinstance(self.user, str) or not re.fullmatch('[a-z_][a-z0-9_-]{0,63}', self.user):
            raise ValueError('ROBOT_USER_INVALID')
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('ROBOT_PORT_INVALID')
        if type(self.ros_domain_id) is not int or not 0 <= self.ros_domain_id <= 232:
            raise ValueError('ROBOT_DOMAIN_INVALID')
        return self

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(asdict(self.checked()), sort_keys=True).encode()).hexdigest()


def checked_record(row):
    expected = {'id', 'label', 'adapter_id', 'endpoint', 'credential_ref', 'discovery_source'}
    optional = {'adapter_version', 'host_identity_ref', 'robot_profile_id', 'calibration_ref', 'battery_display'}
    if (not isinstance(row, dict) or not expected <= set(row) or set(row) - expected - optional or not isinstance(row.get('id'), str)
            or not re.fullmatch('[a-f0-9]{32}', row['id'])):
        raise ValueError('ROBOT_RECORD_INVALID')
    for key in ('label', 'adapter_id', 'credential_ref', 'discovery_source'):
        if not isinstance(row[key], str) or len(row[key]) > 160 or any(ord(c) < 32 for c in row[key]):
            raise ValueError('ROBOT_RECORD_INVALID')
    if not row['label'].strip() or not row['adapter_id'].strip():
        raise ValueError('ROBOT_RECORD_INVALID')
    if not isinstance(row['endpoint'], dict) or set(row['endpoint']) != {'host', 'user', 'port', 'ros_domain_id'}:
        raise ValueError('ROBOT_ENDPOINT_INVALID')
    RobotEndpoint(**row['endpoint']).checked()
    for key in ('adapter_version', 'host_identity_ref', 'robot_profile_id', 'calibration_ref'):
        value = row.get(key)
        if value is not None and (not isinstance(value, str) or len(value)>160 or any(ord(c)<32 for c in value)):
            raise ValueError('ROBOT_RECORD_INVALID')
    if 'battery_display' in row:checked_battery_display(row['battery_display'])
    return deepcopy(row)


class RobotRegistry:
    def __init__(self, state_root):
        self.path = Path(state_root) / 'robot-registry.json'
        self.lock = RLock()
        from .robot_timing_store import RobotTimingStore
        self.timing_store=RobotTimingStore(self.path.parent)
        self._migrate_candidate_battery_settings()

    def _battery_path(self,robot_id):
        if not isinstance(robot_id,str) or not re.fullmatch('[a-f0-9]{32}',robot_id):raise ValueError('ROBOT_NOT_REGISTERED')
        directory=self.path.parent/'robot-battery-displays'
        if directory.is_symlink():raise ValueError('ROBOT_BATTERY_STORAGE_INVALID')
        return directory/(robot_id+'.json')

    def _battery_config(self,row):
        path=self._battery_path(row['id'])
        if path.is_symlink():raise ValueError('ROBOT_BATTERY_STORAGE_INVALID')
        if not path.exists():return record_battery_display(row)
        if path.stat().st_size>16384:raise ValueError('ROBOT_BATTERY_STORAGE_INVALID')
        return checked_battery_display(json.loads(path.read_text(encoding='utf-8')))

    def _write_battery(self,robot_id,config):
        path=self._battery_path(robot_id)
        if path.is_symlink():raise ValueError('ROBOT_BATTERY_STORAGE_INVALID')
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_name('.battery-'+uuid4().hex+'.tmp')
        try:
            with temporary.open('x',encoding='utf-8') as stream:
                json.dump(config,stream,ensure_ascii=False,allow_nan=False)
                stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)

    def _migrate_candidate_battery_settings(self):
        # Early local candidates embedded this optional field in the strict old
        # registry. Move only that field, preserving its exact settings, so older
        # rollback executables can still read the unchanged registry-1.0 shape.
        with self.lock:
            if not self.path.exists():return
            value=self._read()
            if not any('battery_display' in row for row in value['robots']):return
            with self._writer():
                value=self._read()
                for row in value['robots']:
                    if 'battery_display' not in row:continue
                    config=checked_battery_display(row['battery_display'])
                    target=self._battery_path(row['id'])
                    if target.exists() and self._battery_config(row)!=config:raise ValueError('ROBOT_BATTERY_MIGRATION_CONFLICT')
                    self._write_battery(row['id'],config)
                    del row['battery_display']
                self._publish_locked(value,value['revision'])

    def _read(self):
        if not self.path.exists():
            return dict(schema_version='robot-registry-1.0', revision=0, active_id=None, robots=[])
        if self.path.is_symlink() or self.path.stat().st_size > 262144:
            raise ValueError('ROBOT_REGISTRY_INVALID')
        value = json.loads(self.path.read_text(encoding='utf-8'))
        if (set(value) != {'schema_version', 'revision', 'active_id', 'robots'}
                or value['schema_version'] != 'robot-registry-1.0'
                or type(value['revision']) is not int or value['revision'] < 0
                or not isinstance(value['robots'], list) or len(value['robots']) > 100):
            raise ValueError('ROBOT_REGISTRY_INVALID')
        rows = [checked_record(r) for r in value['robots']]
        ids = [r['id'] for r in rows]
        if len(ids) != len(set(ids)) or value['active_id'] is not None and value['active_id'] not in ids:
            raise ValueError('ROBOT_REGISTRY_INVALID')
        return value

    def snapshot(self):
        with self.lock:
            value = deepcopy(self._read())
            for row in value['robots']:
                row.pop('credential_ref')
                row['battery_display']=self._battery_config(row)
                row['battery_display_sha256']=battery_display_sha256(row['battery_display'])
                from .robot_adapters import instance_binding
                try:row['timing_settings']=self.timing_store.read(row['id'],instance_binding(row)['sha256'])
                except (ValueError,KeyError,OSError):
                    row['timing_settings']=None
                    row['timing_settings_error']='Saved adapter/binding or timing data needs review; no settings or authority restored.'
                row.update(connection_state='unverified', motion_authorized=False)
            return value

    def active(self):
        with self.lock:
            value = self._read()
            return next((deepcopy(r) for r in value['robots'] if r['id'] == value['active_id']), None)

    def active_at_revision(self, expected_revision):
        """Pin revision and endpoint from one atomic-file snapshot for execution."""
        with self.lock:
            value=self._read()
            if type(expected_revision) is not int or value['revision'] != expected_revision:
                raise ValueError('ROBOT_REGISTRY_CHANGED')
            return next((deepcopy(row) for row in value['robots'] if row['id']==value['active_id']),None)

    @contextmanager
    def _writer(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name('robot-registry.writer-lock')
        if lock_path.is_symlink():
            raise ValueError('ROBOT_REGISTRY_LOCK_INVALID')
        with lock_path.open('a+b') as stream:
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b'0'); stream.flush()
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise ValueError('ROBOT_REGISTRY_BUSY') from None
                try:
                    yield
                finally:
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise ValueError('ROBOT_REGISTRY_BUSY') from None
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _publish(self, value, expected_revision):
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('ROBOT_REVISION_INVALID')
        with self._writer():
            self._publish_locked(value, expected_revision)

    def _publish_locked(self, value, expected_revision):
        if self._read()['revision'] != expected_revision:
            raise ValueError('ROBOT_REGISTRY_CHANGED')
        value['revision'] = expected_revision + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name('.robot-registry-' + uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def register(self, *, label, adapter_id, endpoint, credential_ref='', discovery_source='manual', expected_revision,
                 adapter_version=None, host_identity_ref='openssh-known-hosts', robot_profile_id=None, calibration_ref=None):
        row = checked_record(dict(id=uuid4().hex, label=label, adapter_id=adapter_id,
            endpoint=asdict(endpoint.checked()), credential_ref=credential_ref, discovery_source=discovery_source,
            adapter_version=adapter_version, host_identity_ref=host_identity_ref,
            robot_profile_id=robot_profile_id, calibration_ref=calibration_ref))
        with self.lock:
            value = self._read()
            if len(value['robots']) >= 100:
                raise ValueError('ROBOT_REGISTRY_FULL')
            value['robots'].append(row)
            self._publish(value, expected_revision)
            return deepcopy(row)

    def select(self, robot_id, *, expected_revision, assert_workspace_idle):
        # Caller must own WorkspaceDevices.lock through endpoint service rebuild
        # and credential rebinding. This guard is supplementary, not that lock.
        with self.lock:
            assert_workspace_idle()
            value = self._read()
            if robot_id is not None and not any(r['id'] == robot_id for r in value['robots']):
                raise ValueError('ROBOT_NOT_REGISTERED')
            value['active_id'] = robot_id
            self._publish(value, expected_revision)
            return self.active()

    def set_battery_display(self, robot_id, config, *, expected_revision, expected_display_sha256):
        checked=checked_battery_display(config)
        with self.lock,self._writer():
            value=self._read()
            if type(expected_revision) is not int or value['revision']!=expected_revision:raise ValueError('ROBOT_REGISTRY_CHANGED')
            row=next((r for r in value['robots'] if r['id']==robot_id),None)
            if row is None:raise ValueError('ROBOT_NOT_REGISTERED')
            # Config hash also catches a process crash between the two atomic
            # local publishes. A stale client never overwrites that saved edit.
            if battery_display_sha256(self._battery_config(row))!=expected_display_sha256:raise ValueError('ROBOT_REGISTRY_CHANGED')
            self._write_battery(robot_id,checked)
            self._publish_locked(value,expected_revision)
            return deepcopy(checked)

    def timing_action(self,robot_id,*,expected_revision,expected_sha256,values=None,mode=None,measurement=None,operation_id=None,origin=None,
                      recalculate=False,expected_recommendation_sha256=None):
        from .robot_adapters import instance_binding
        with self.lock,self._writer():
            value=self._read()
            if type(expected_revision) is not int or expected_revision!=value['revision']:raise ValueError('ROBOT_REGISTRY_CHANGED')
            row=next((r for r in value['robots'] if r['id']==robot_id),None)
            if row is None:raise ValueError('ROBOT_NOT_REGISTERED')
            binding=instance_binding(row)
            current=self.timing_store.read(robot_id,binding['sha256'])
            if current['profile_sha256']!=expected_sha256:raise ValueError('ROBOT_REGISTRY_CHANGED')
            if recalculate:
                result=self.timing_store.recalculate(robot_id,binding['sha256'])
            elif measurement is not None:
                result=self.timing_store.record(robot_id,binding['sha256'],operation_id,measurement,origin=origin)
            else:
                result=self.timing_store.edit(robot_id,binding['sha256'],values,mode,expected_sha256,expected_recommendation_sha256)
            self._publish_locked(value,expected_revision)
            return result

    def record_timing_measurement(self,robot_id,binding_sha256,operation_id,measurement):
        from .robot_adapters import instance_binding
        # Cleanup can be joined while the pool entry lock is held. A simultaneous
        # UI selection holds registry.lock while checking that entry. Do not
        # create entry -> reader -> registry -> entry inversion. The cross-
        # process writer lock and revision CAS still serialize atomic publishes;
        # there is no shared mutable in-memory registry state to protect here.
        with self._writer():
            value=self._read();row=next((r for r in value['robots'] if r['id']==robot_id),None)
            if row is None or instance_binding(row)['sha256']!=binding_sha256:raise ValueError('TIMING_BINDING_CHANGED')
            result=self.timing_store.record(robot_id,binding_sha256,operation_id,measurement,origin='AUTHENTICATED_SESSION_PASSIVE_SOFTWARE_TIMING')
            self._publish_locked(value,value['revision'])
            return result


def enumerate_windows_devices():
    """Enumerate OS-known serial mappings; do not open COM or pair BLE.

    A Bluetooth radio search and network service discovery are separate future
    adapters. Their absence is explicit instead of returning a false live scan.
    """
    result = dict(schema_version='robot-discovery-1.0', candidates=[],
                  network_state='NOT_IMPLEMENTED', bluetooth_state='NOT_IMPLEMENTED',
                  serial_state='UNAVAILABLE', connected=False)
    if os.name != 'nt':
        return result
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DEVICEMAP\SERIALCOMM') as key:
            for index in range(winreg.QueryInfoKey(key)[1]):
                device, port, _kind = winreg.EnumValue(key, index)
                if isinstance(port, str) and re.fullmatch(r'COM[0-9]{1,5}', port):
                    result['candidates'].append(dict(candidate_id=hashlib.sha256(device.encode()).hexdigest(),
                        transport='serial', address=port, label=port, identity_verified=False,
                        adapter_id=None, connection_state='not_connected'))
        result['serial_state'] = 'OS_ENUMERATED'
    except FileNotFoundError:
        result['serial_state'] = 'OS_ENUMERATED'
    except OSError:
        result['serial_state'] = 'ACCESS_UNAVAILABLE'
    return result
