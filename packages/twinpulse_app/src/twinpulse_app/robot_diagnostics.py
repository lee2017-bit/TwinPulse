# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit PC preflight and single-flight read-only robot observation jobs.

No connection on construction, snapshot or PC preflight. No motor/driver/deploy
actions. Transport implementation is shared with the existing reviewed CLI.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import secrets
import shutil
from threading import RLock, Thread
import time
import sys

from .command_broker import BrokerError
from .robot_reports import RobotReports


def connection_failure(result):
    """Classify bounded SSH diagnostics without copying arbitrary remote stderr.

    Unknown remote output can contain private material; keep the original exit
    code and a safe classification, never key paths or uncontrolled text.
    """
    reason = str(result.get('reason', ''))[-4096:].lower()
    patterns = (('connection refused', 'SSH_CONNECTION_REFUSED'),
                ('connection timed out', 'SSH_CONNECT_TIMEOUT'),
                ('no route to host', 'SSH_NO_ROUTE'),
                ('network is unreachable', 'SSH_NO_ROUTE'),
                ('host key verification failed', 'SSH_HOST_KEY_REJECTED'),
                ('remote host identification has changed', 'SSH_HOST_KEY_REJECTED'),
                ('permission denied', 'SSH_AUTH_FAILED'),
                ('could not resolve hostname', 'SSH_NAME_RESOLUTION_FAILED'))
    code = next((code for pattern, code in patterns if pattern in reason),
                'CONNECTION_CHECK_TIMEOUT' if result.get('status') == 'CONNECTION_CHECK_TIMEOUT'
                else result.get('status', 'CHECK_FAILED'))
    exit_code = result.get('exit_code')
    return {'code': code, 'exit_code': exit_code if type(exit_code) is int else None}


class RobotDiagnostics:
    def __init__(self, root, *, identity=None, known_hosts=None, collector=None,
                 which=shutil.which, clock=time.monotonic, archive_root=None):
        self.root = Path(root).resolve()
        self.archive_root = Path(archive_root).resolve() if archive_root is not None else self.root
        self.identity = identity or Path.home()/'.ssh/twinpulse-burger/id_ed25519_automation'
        self.known_hosts = known_hosts or Path.home()/'.ssh/known_hosts'
        self.which, self.clock = which, clock
        self._collector = collector
        self._lock = RLock()
        self._thread = None
        self._closed = False
        self._prepared = None
        self._owner = None
        self._token = None
        self._consumed = None
        self._fingerprint = None
        self._expires = 0
        self._job = None
        self._reports = RobotReports()
        self._local_release_id = None

    def _pc(self):
        # The currently shipped robot source identity is local-only. It does not
        # qualify motion; the UI uses it to avoid offering a mode absent from an
        # older robot release.
        try:
            spec = importlib.util.spec_from_file_location('robot_source_identity', self.root/'scripts/robot_source_identity.py')
            source = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(source)
            self._local_release_id = source.source_id(self.root)
        except (OSError, AttributeError, ValueError):
            self._local_release_id = None
        files = [self.root/'scripts'/name for name in
                 ('check_robot_connection.py', 'robot_health.py', 'turtlebot_probe.py')]
        ssh = self.which('ssh.exe' if sys.platform == 'win32' else 'ssh')
        checks = [{'id': 'checker_sources', 'ok': all(p.is_file() for p in files)},
                  {'id': 'ssh_client', 'ok': bool(ssh)},
                  {'id': 'identity_file', 'ok': self.identity.is_file()},
                  {'id': 'known_hosts_file', 'ok': self.known_hosts.is_file()}]
        # Key contents are never opened. Metadata only; host identity is verified
        # by StrictHostKeyChecking=yes during the explicitly requested SSH read.
        material = [ssh]
        for p in files:
            material.append(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
        for p in (self.identity, self.known_hosts):
            s = p.stat() if p.is_file() else None
            material.append((str(p), s.st_size, s.st_mtime_ns) if s else None)
        return checks, hashlib.sha256(repr(material).encode()).hexdigest()

    def snapshot(self, owner):
        with self._lock:
            ready = bool(not self._closed and self._token and owner == self._owner
                         and self.clock() < self._expires and not self._running())
            return {'schema_version': 'robot-diagnostics-1.0', 'available': not self._closed,
                    'target': 'twinpulse@192.168.35.139', 'motion_authorized': False,
                    'demo_ready': False, 'pc': deepcopy(self._prepared),
                    'local_release_id': self._local_release_id,
                    'start_token': self._token if ready else None,
                    'job': deepcopy(self._job), 'record': self._reports.snapshot()['record']}

    def _running(self):
        return bool(self._job and self._job['status'] == 'RUNNING')

    def preflight(self, owner):
        with self._lock:
            if self._closed or self._running():
                raise BrokerError('robot_check_busy', 'A check is running or the service is closed.', status=409)
            self._token = None
            try:
                checks, fingerprint = self._pc()
            except OSError:
                checks, fingerprint = [{'id': 'pc_file_access', 'ok': False}], None
            self._prepared = {'ready': all(c['ok'] for c in checks), 'checks': checks,
                              'checked_at_utc': datetime.now(timezone.utc).isoformat()}
            self._owner = owner
            self._fingerprint = fingerprint
            self._expires = self.clock() + 120
            if self._prepared['ready']:
                self._token = secrets.token_urlsafe(24)
            return self.snapshot(owner)

    def start(self, owner, token, confirmed):
        with self._lock:
            if self._closed:
                raise BrokerError('robot_check_closed', 'Service is closed.', status=409)
            if confirmed is not True or not isinstance(token, str) or owner != self._owner:
                raise BrokerError('robot_check_confirmation', 'Explicit read-only confirmation required.', status=409)
            # Lost HTTP replies cannot cause duplicate runs, including after completion.
            if (owner, token) == self._consumed:
                return self.snapshot(owner)
            if self._running() or token != self._token or self.clock() >= self._expires:
                raise BrokerError('robot_preflight_required', 'Run PC preparation again.', status=409)
            try:
                checks, fingerprint = self._pc()
            except OSError:
                checks, fingerprint = [], None
            if not checks or not all(c['ok'] for c in checks) or fingerprint != self._fingerprint:
                self._token = None
                raise BrokerError('robot_preflight_changed', 'PC preparation changed; check again.', status=409)
            self._consumed, self._token = (owner, token), None
            self._reports = RobotReports()  # Old voltage must not survive a new failed attempt.
            self._job = {'id': secrets.token_hex(12), 'status': 'RUNNING',
                         'phase': 'READ_ONLY_CHECK', 'started_at_utc': datetime.now(timezone.utc).isoformat(),
                         'result_code': None, 'saved': False}
            self._thread = Thread(target=self._run, daemon=True, name='TwinPulseReadOnlyCheck')
            self._thread.start()
            return self.snapshot(owner)

    def _run(self):
        code, status, saved = 'CHECK_FAILED', 'FAILED', False
        try:
            spec = importlib.util.spec_from_file_location('twinpulse_readonly_cli', self.root/'scripts/check_robot_connection.py')
            cli = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cli)
            collect = self._collector or cli.collect_readonly
            result = collect('192.168.35.139', 'twinpulse', identity_file=self.identity)
            allowed = {'SSH_CLIENT_MISSING', 'SSH_OR_REMOTE_SETUP_FAILED', 'CONNECTION_CHECK_TIMEOUT', 'CHECK_FAILED'}
            if result.get('status') in allowed:
                code = result['status']
                with self._lock:
                    self._job['diagnostic'] = connection_failure(result)
            else:
                record = self._reports.import_report(result)['record']
                code = 'OBSERVATION_RECEIVED'
                status = 'COMPLETED'
                health = result.get('health', {})
                health_code = health.get('status')
                if health_code not in {'IDLE_SNAPSHOT_OK', 'NEEDS_ATTENTION', 'READ_ONLY_SNAPSHOT', 'SNAPSHOT_COLLECTED'}:
                    health_code = 'UNKNOWN'
                sensor_code = result.get('status')
                if sensor_code not in {'SENSOR_MESSAGES_RECEIVED', 'PARTIAL_SENSOR_DATA', 'NO_SENSOR_DATA',
                                       'ROS_PYTHON_UNAVAILABLE', 'ROS_PROBE_FAILED'}:
                    sensor_code = 'UNKNOWN'
                with self._lock:
                    self._job['health_status'] = health_code
                    self._job['sensor_status'] = sensor_code
                if (not record or record['idle_at_observation'] is not True
                        or health_code != 'IDLE_SNAPSHOT_OK'
                        or not record['guard_artifact_verified_at_observation']
                        or not record['release_id']
                        or (record['battery'] and (record['battery']['charge_requested_at_observation']
                            or record['battery']['near_protection_at_observation']))):
                    code = 'OBSERVATION_NEEDS_ATTENTION'
            # Save only normalized display data, not remote stdout/key paths.
            with self._lock:
                output = self.archive_root/'artifacts/robot-console'/self._job['id']
            import json
            output.mkdir(parents=True, exist_ok=False)
            (output/'report.json').write_text(json.dumps({'result_code': code,
                'schema_version': 'robot-console-result-1.1',
                'health_status': self._job.get('health_status'),
                'sensor_status': self._job.get('sensor_status'),
                'diagnostic': self._job.get('diagnostic'),
                'motion_authorized': False, 'record': self._reports.snapshot()['record']}, indent=2), encoding='utf-8')
            saved = True
        except Exception:
            code, status = 'CHECK_OR_SAVE_FAILED', 'FAILED'
        finally:
            with self._lock:
                self._job.update(status=status, phase='FINISHED', result_code=code, saved=saved,
                                 finished_at_utc=datetime.now(timezone.utc).isoformat())

    def close(self):
        with self._lock:
            self._closed = True
            self._token = None
        # The shared collector bounds and reaps its own SSH child at120s.
        if self._thread:
            self._thread.join(timeout=125)
