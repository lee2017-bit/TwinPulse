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
import re
import math
from twinpulse_core import canonical_sha256
from twinpulse_core.execution_diagnostics import ExecutionStore

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
        from .robot_adapters import legacy_binding
        self._instance = legacy_binding()
        self.execution_logs=ExecutionStore(self.archive_root/'artifacts/robot-diagnostics','robot_devices')
        self._trace=None
        self._observation_catalog_cache=None

    def observation_catalog(self,instance_id):
        if instance_id is None:return []
        folder=self.archive_root/'artifacts/robot-console'
        paths=sorted(folder.glob('*/report.json')) if folder.exists() else []
        stamp=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
        key=(instance_id,stamp)
        if self._observation_catalog_cache and self._observation_catalog_cache[0]==key:
            return deepcopy(self._observation_catalog_cache[1])
        rows=[]
        for path in sorted(paths,key=lambda p:p.stat().st_mtime_ns,reverse=True):
            try:
                value=self.observation(path.parent.name)
                if (value.get('robot_binding') or {}).get('instance_id')!=instance_id:continue
                rows.append(dict(job_id=value['job_id'],execution_id=value['execution_id'],
                    result_code=value['result_code'],finished_at_utc=value['finished_at_utc'],
                    scan_count=len((value.get('obstacle_observation') or {}).get('scans',[]))))
                if len(rows)>=20:break
            except (OSError,ValueError,TypeError,KeyError,BrokerError):continue
        self._observation_catalog_cache=(key,deepcopy(rows))
        return rows

    def observation(self,job_id):
        """Local data export; reading a log never starts a connection."""
        return self._observation_source(job_id)[0]

    def observation_export(self,job_id):
        value,raw=self._observation_source(job_id)
        return dict(schema_version='robot-observation-export-1.0',job_id=job_id,
            export_sha256=value['sha256'],file_sha256=hashlib.sha256(raw).hexdigest(),
            json_text=raw.decode('utf-8'))

    def _observation_source(self,job_id):
        if not isinstance(job_id,str) or not re.fullmatch('[a-f0-9]{24}',job_id):
            raise BrokerError('robot_observation_invalid','Observation ID is invalid.',status=400)
        folder=self.archive_root/'artifacts/robot-console'/job_id;path=folder/'report.json'
        if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file() or path.stat().st_size>4*1024*1024:
            raise BrokerError('robot_observation_unavailable','No saved observation log is available.',status=404)
        import json
        with path.open('rb') as stream:raw=stream.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:
            raise BrokerError('robot_observation_unavailable','Saved observation exceeds the export limit.',status=409)
        value=json.loads(raw.decode('utf-8'))
        if value.get('schema_version')!='robot-console-result-1.2' or value.get('job_id')!=job_id:
            raise BrokerError('robot_observation_unavailable','This older observation has no sensor export. Run a new connection check.',status=409)
        digest=value.pop('sha256',None)
        if canonical_sha256(value)!=digest:raise BrokerError('robot_observation_changed','Saved observation bytes changed.',status=409)
        return {**value,'sha256':digest},raw

    def bind_instance(self, binding):
        from .robot_adapters import checked_binding
        with self._lock:
            if self._running():
                raise BrokerError('robot_check_busy', 'Wait for the current observation before selecting another robot.', status=409)
            binding = checked_binding(binding) if binding is not None else None
            if binding == self._instance:return
            self._instance = binding
            self._token = self._consumed = self._owner = self._prepared = self._fingerprint = None
            self._expires = 0
            self._job = None
            self._reports = RobotReports()

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
        material = [ssh, self._instance['sha256'] if self._instance else None]
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
                    'target': f"{self._instance['endpoint']['user']}@{self._instance['endpoint']['host']}" if self._instance else None,
                    'robot_binding': deepcopy(self._instance), 'motion_authorized': False,
                    'demo_ready': False, 'pc': deepcopy(self._prepared),
                    'local_release_id': self._local_release_id,
                    'start_token': self._token if ready else None,
                    'job': deepcopy(self._job), 'record': self._reports.snapshot()['record']}

    def _running(self):
        return bool(self._job and self._job['status'] == 'RUNNING')

    def preflight(self, owner):
        with self._lock:
            from .robot_adapters import require_adapter
            require_adapter(self._instance)
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
                         'robot_binding': deepcopy(self._instance), 'authentication_verified': False,
                         'phase': 'READ_ONLY_CHECK', 'started_at_utc': datetime.now(timezone.utc).isoformat(),
                         'result_code': None, 'saved': False}
            self._trace=self.execution_logs.begin('robot_read_only_check',robot_session_id=self._job['id'],artifact_id=self._job['id'])
            self._job['execution_id']=self._trace.execution_id
            self._thread = Thread(target=self._run, daemon=True, name='TwinPulseReadOnlyCheck')
            self._thread.start()
            return self.snapshot(owner)

    def _run(self):
        code, status, saved = 'CHECK_FAILED', 'FAILED', False
        sensor=None;odometry=[];events=[]
        def event(phase,code):
            if code not in {'READ_ONLY_SSH','CHECK_FAILED','SSH_CLIENT_MISSING','SSH_OR_REMOTE_SETUP_FAILED',
                    'CONNECTION_CHECK_TIMEOUT','ROS_PYTHON_UNAVAILABLE','SENSOR_MESSAGES_RECEIVED','PARTIAL_SENSOR_DATA',
                    'NO_SENSOR_DATA','ROS_PROBE_FAILED','OBSERVATION_RECEIVED','OBSERVATION_NEEDS_ATTENTION'}:
                code='UNRECOGNIZED_RESPONSE'
            events.append(dict(at_utc=datetime.now(timezone.utc).isoformat(),phase=phase,code=code))
            if self._trace:self._trace.child(phase,error_code=code).finish('succeeded')
        try:
            event('connection_started','READ_ONLY_SSH')
            spec = importlib.util.spec_from_file_location('twinpulse_readonly_cli', self.root/'scripts/check_robot_connection.py')
            cli = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cli)
            collect = self._collector or cli.collect_readonly
            from .robot_adapters import require_adapter
            target = require_adapter(self._job['robot_binding'])
            result = collect(target.host, target.user, identity_file=self.identity,
                             domain_id=target.ros_domain_id, port=target.port, known_hosts=self.known_hosts)
            event('connection_returned',str(result.get('status','CHECK_FAILED')))
            if (result.get('obstacle_observation') or {}).get('scans'):
                from twinpulse_core.obstacle_feedback import checked_observation
                sensor=checked_observation(result['obstacle_observation'])
                # The source is a read-only SSH observation only with the real
                # reviewed collector. Injected transport is never hardware proof.
                if self._collector is not None:sensor['provenance']='IMPORTED_SENSOR'
                for row in (result.get('odometry_samples') or [])[:16]:
                    if not isinstance(row,dict):continue
                    keys={'stamp_ns','frame_id','child_frame_id','position_m','orientation_xyzw','linear_x','angular_z'}
                    if set(row)!=keys or type(row['stamp_ns']) is not int or not 0<row['stamp_ns']<2**63:continue
                    if any(not isinstance(row[k],str) or not re.fullmatch('[A-Za-z0-9_/-]{1,128}',row[k]) for k in ('frame_id','child_frame_id')):continue
                    if not isinstance(row['position_m'],list) or len(row['position_m'])!=3 or not isinstance(row['orientation_xyzw'],list) or len(row['orientation_xyzw'])!=4:continue
                    if any(type(v) not in (int,float) or not math.isfinite(v) for v in row['position_m']+row['orientation_xyzw']+[row['linear_x'],row['angular_z']]):continue
                    odometry.append(deepcopy(row))
                self._job['scan_count']=len(sensor['scans'])
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
                    self._job['authentication_verified'] = self._collector is None
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
            event('observation_saved',code)
            value={'result_code': code,'job_id':self._job['id'],'execution_id':self._job['execution_id'],
                'schema_version': 'robot-console-result-1.2',
                'robot_binding': self._job['robot_binding'],
                'health_status': self._job.get('health_status'),
                'sensor_status': self._job.get('sensor_status'),
                'diagnostic': self._job.get('diagnostic'),
                'motion_authorized': False, 'record': self._reports.snapshot()['record'],
                'obstacle_observation':sensor,'odometry_samples':odometry,'events':events,
                'started_at_utc':self._job['started_at_utc'],'finished_at_utc':datetime.now(timezone.utc).isoformat(),
                'sensor_pose_verified':False,'alignment_verified':False,'physical_authority':False}
            value['sha256']=canonical_sha256(value)
            (output/'report.json').write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
            saved = True
        except Exception as error:
            code, status = 'CHECK_OR_SAVE_FAILED', 'FAILED'
            if self._trace:self._trace.bind(error_type=type(error).__name__)
            # Failed transports/parsers still leave an execution-bound record.
            # Keep only typed cause information, never uncontrolled SSH stderr.
            try:
                import json
                output=self.archive_root/'artifacts/robot-console'/self._job['id']
                output.mkdir(parents=True,exist_ok=True)
                value=dict(schema_version='robot-console-result-1.2',job_id=self._job['id'],
                    execution_id=self._job['execution_id'],robot_binding=self._job['robot_binding'],
                    result_code=code,error_type=type(error).__name__,events=events,obstacle_observation=sensor,
                    odometry_samples=[],record=None,motion_authorized=False,physical_authority=False,
                    started_at_utc=self._job['started_at_utc'],finished_at_utc=datetime.now(timezone.utc).isoformat())
                value['sha256']=canonical_sha256(value)
                with (output/'report.json').open('x',encoding='utf-8') as stream:
                    json.dump(value,stream,allow_nan=False)
                saved=True
            except (OSError,TypeError,ValueError):pass
        finally:
            with self._lock:
                self._job.update(status=status, phase='FINISHED', result_code=code, saved=saved,
                                 finished_at_utc=datetime.now(timezone.utc).isoformat())
                if self._trace:self._trace.finish('succeeded' if status=='COMPLETED' else 'failed',
                    error_code=code,persisted=saved,artifact_id=self._job['id'])
                self.execution_logs.flush()

    def close(self):
        with self._lock:
            self._closed = True
            self._token = None
        # The shared collector bounds and reaps its own SSH child at120s.
        if self._thread:
            self._thread.join(timeout=125)
