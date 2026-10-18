# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit persistent SSH session. No transport/device work in constructors.

Only reviewed shipped sources enter the versioned robot-user cache. The existing
robot/current release and system installations are never replaced. The remote
worker, not PC telemetry or a UI flag, admits motor commands.
"""
from copy import deepcopy
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
from uuid import uuid4

from .command_broker import BrokerError
from .robot_adapters import checked_binding, require_adapter
from twinpulse_core.robot_lineage import checked_twin_context

SCHEMA = 'physical-live-event-1.0'
MAX_LINE = 256 * 1024
BOOTSTRAP = r'''
import base64,hashlib,json,os,pathlib,re,runpy,sys
line=sys.stdin.buffer.readline(16*1024*1024+1)
if len(line)>16*1024*1024: raise ValueError('BOOTSTRAP_BYTE_LIMIT')
packet=json.loads(line)
if set(packet)!={'schema','files','sha256'} or packet['schema']!='physical-live-bundle-1.0': raise ValueError('BOOTSTRAP_SHAPE')
files=packet['files']
if not isinstance(files,dict) or not 1<=len(files)<=160: raise ValueError('BOOTSTRAP_FILE_LIMIT')
decoded={}
for name,item in files.items():
 if not isinstance(name,str) or not (re.fullmatch(r'(?:twinpulse_core/)?[a-zA-Z0-9_.-]+\.(?:py|sh|json)',name) or name in {'LICENSE.txt','NOTICE.txt','THIRD_PARTY_NOTICES.txt'}): raise ValueError('BOOTSTRAP_PATH')
 if not isinstance(item,dict) or set(item)!={'base64','sha256'}: raise ValueError('BOOTSTRAP_ITEM')
 data=base64.b64decode(item['base64'],validate=True)
 if len(data)>2*1024*1024 or hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('BOOTSTRAP_FILE_SHA')
 decoded[name]=data
digests={k:hashlib.sha256(v).hexdigest() for k,v in decoded.items()}
digest=hashlib.sha256(json.dumps(digests,sort_keys=True,separators=(',',':')).encode()).hexdigest()
if digest!=packet['sha256']: raise ValueError('BOOTSTRAP_BUNDLE_SHA')
root=pathlib.Path.home()/'.local/share/twinpulse/fleet/releases'
root.mkdir(parents=True,exist_ok=True,mode=0o700)
if root.is_symlink() or any(p.is_symlink() for p in [root.parent,root.parent.parent]): raise ValueError('BOOTSTRAP_CACHE_SYMLINK')
release=root/digest
release.mkdir(exist_ok=True,mode=0o700)
for name,data in decoded.items():
 path=release/name
 path.parent.mkdir(exist_ok=True,mode=0o700)
 if path.is_symlink() or path.parent.is_symlink(): raise ValueError('BOOTSTRAP_MEMBER_SYMLINK')
 if path.exists():
  if not path.is_file() or path.read_bytes()!=data: raise ValueError('BOOTSTRAP_CACHE_CHANGED')
 else:
  with path.open('xb') as f: f.write(data)
sys.path.insert(0,str(release))
os.environ['TWINPULSE_FLEET_BUNDLE_SHA256']=digest
runpy.run_path(str(release/'fleet_worker.py'),run_name='__main__')
'''


def reviewed_bundle(root):
    """Build from fixed source roots, not user paths or model-written commands."""
    root = Path(root)
    package = root / 'packages/twinpulse_robot_safety'
    names = ('fleet_worker.py', 'fleet_control.py', 'native_stream.py', 'physical_profile.py', 'field_tests.py',
             'teleop_ros.py', 'teleop_contract.py', 'teleop_worker.py', 'stop_policy.py',
             'lidar_capture.py', 'robot_journal.py', 'raw_ros_record.py', 'robot_session.py',
             'runtime.py', 'stationary.py', 'owned_exec.py','cleanup_notes.py','control_timing.py','field_config.py')
    files = {}
    for name,target in (('LICENSE','LICENSE.txt'),('NOTICE','NOTICE.txt'),('THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.txt')):
        path=root/name
        if path.is_symlink() or not path.is_file():raise ValueError('LIVE_SOURCE_NOTICE_MISSING')
        files[target]=path.read_bytes()
    for name in names:
        path = package / name
        if not path.is_file():
            # Optional helpers may not exist in this source revision. Required
            # worker imports are checked before any transport starts below.
            continue
        if path.is_symlink(): raise ValueError('LIVE_SOURCE_SYMLINK')
        files[name] = path.read_bytes()
    for name in ('fleet_worker.py', 'fleet_control.py', 'native_stream.py'):
        if name not in files: raise ValueError('LIVE_REVIEWED_WORKER_MISSING:' + name)
    health = root / 'scripts/robot_health.py'
    if health.is_file(): files['robot_health.py'] = health.read_bytes()
    core = root / 'packages/twinpulse_core/src/twinpulse_core'
    pending = ['manual_motion_guard', 'local_navigation', 'ros_observations', 'navigation_binding', 'observation_stream', 'robot_lineage','field_persistence']
    import ast
    files['twinpulse_core/__init__.py'] = b'"""Pure shipped contracts; no device initialization."""\n'
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen: continue
        if not name.isidentifier(): raise ValueError('LIVE_CORE_IMPORT')
        seen.add(name)
        path = core / (name + '.py')
        if path.is_symlink(): raise ValueError('LIVE_CORE_SYMLINK')
        data = path.read_bytes()
        files['twinpulse_core/' + name + '.py'] = data
        # Existing robot modules also import these contracts as top-level names.
        files[name + '.py'] = data
        for node in ast.walk(ast.parse(data)):
            if isinstance(node, ast.ImportFrom) and node.level:
                if node.level != 1 or not node.module: raise ValueError('LIVE_CORE_IMPORT')
                pending.append(node.module.split('.')[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('twinpulse_core.'):
                pending.append(node.module.split('.')[1])
    digests = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
    sha = hashlib.sha256(json.dumps(digests, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    packet = dict(schema='physical-live-bundle-1.0', sha256=sha,
                  files={k: dict(base64=base64.b64encode(v).decode(), sha256=digests[k]) for k, v in files.items()})
    encoded = (json.dumps(packet, separators=(',', ':')) + '\n').encode()
    if len(encoded) > 16 * 1024 * 1024: raise ValueError('LIVE_BUNDLE_BYTE_LIMIT')
    return sha, encoded, digests


class StreamEvidence:
    """Bounded async rotating bytes; disk/fsync never owns a Stop/state lock."""
    def __init__(self, directory, *, segment_bytes=4*1024*1024, maximum_bytes=256*1024*1024):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.segment_bytes, self.maximum_bytes = segment_bytes, maximum_bytes
        self.lock = threading.RLock()
        self.stream = None
        self.rows, self.count, self.total, self.size = [], 0, 0, 0
        self.error = None
        self.closed = self.finalized = False
        self.accepted=self.reserved=self.pending_bytes=0
        self.cleanup_confirmed=False
        self.queue=queue.Queue(maxsize=1024)
        self.cached=dict(schema='physical-live-recording-1.0',directory=self.directory.name,
                         event_count=0,bytes=0,segments=[],complete=False,error=None,accepted=0,saved=0)
        self.thread=threading.Thread(target=self._write,daemon=True,name='physical-evidence-writer')
        self.thread.start()

    def _publish(self):
        # Only the disk thread reads rows. Readers consume an immutable value
        # without acquiring the admission lock or waiting for filesystem I/O.
        self.cached=dict(schema='physical-live-recording-1.0',directory=self.directory.name,
            event_count=self.count,bytes=self.total,segments=deepcopy(self.rows),
            complete=self.finalized and self.error is None and self.accepted==self.count,
            error=self.error,accepted=self.accepted,saved=self.count)

    def _finish(self):
        if self.stream is None: return
        self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()
        self.rows[-1].update(bytes=self.size, sha256=self.digest.hexdigest(), events=self.segment_count)
        self.stream = None

    def append(self, raw):
        with self.lock:
            if self.closed or self.error: return False
            try:
                if not isinstance(raw,bytes) or len(raw)>MAX_LINE or self.reserved+len(raw)>self.maximum_bytes or self.pending_bytes+len(raw)>16*1024*1024:
                    raise ValueError('STREAM_RECORDING_CAPACITY')
                self.queue.put_nowait(raw)
                self.accepted+=1;self.reserved+=len(raw);self.pending_bytes+=len(raw)
                return True
            except (ValueError,queue.Full) as error:
                self.error=type(error).__name__+':'+str(error)[:100]
                return False

    def _write(self):
        try:
            while True:
                try:raw=self.queue.get(timeout=.05)
                except queue.Empty:
                    if self.closed:break
                    continue
                if self.stream is None or self.size + len(raw) > self.segment_bytes:
                    self._finish()
                    name = f'events-{len(self.rows):05d}.jsonl'
                    self.stream = (self.directory / name).open('xb')
                    self.rows.append(dict(path=name)); self.size = self.segment_count = 0
                    self.digest = hashlib.sha256()
                if self.stream.write(raw) != len(raw): raise OSError('STREAM_SHORT_WRITE')
                self.digest.update(raw); self.size += len(raw); self.total += len(raw)
                self.segment_count += 1; self.count += 1
                with self.lock:self.pending_bytes-=len(raw)
                self._publish()
        except (OSError,ValueError) as error:self.error=type(error).__name__+':'+str(error)[:100]
        finally:
            try:self._finish()
            except OSError as error:self.error='FINAL_FLUSH:'+type(error).__name__
            if not self.cleanup_confirmed and self.error is None:self.error='REMOTE_CLEANUP_UNCONFIRMED'
            self.finalized=True;self._publish()
            try:
                with (self.directory/'receipt.json').open('x',encoding='utf-8') as stream:
                    json.dump(self.cached,stream,indent=2);stream.flush();os.fsync(stream.fileno())
            except OSError:self.error='RECEIPT_WRITE_FAILED';self._publish()

    def snapshot(self):
        return dict(deepcopy(self.cached),error=self.error,complete=self.cached['complete'] and self.error is None)

    def close(self, *, cleanup_confirmed):
        with self.lock:
            self.cleanup_confirmed=cleanup_confirmed;self.closed=True
        self.thread.join(timeout=2)
        if self.thread.is_alive():self.error=self.error or 'FINAL_FLUSH_PENDING'
        return self.snapshot()


class PhysicalLiveSession:
    def __init__(self, source_root, archive_root, *, identity, known_hosts,
                 process_factory=subprocess.Popen, clock=time.monotonic, wall=time.time):
        self.source_root, self.archive_root = Path(source_root), Path(archive_root)
        self.identity, self.known_hosts = Path(identity), Path(known_hosts)
        self.factory, self.clock, self.wall = process_factory, clock, wall
        self.lock = threading.RLock(); self.binding = self.context = None
        self.thread = self.process = self.evidence = None
        self.writes = queue.Queue(maxsize=16)
        self.last = {}; self.scan = None; self.scan_at = None; self.at = self.battery_at = None
        self.motion_epoch=None
        self.watch_ack_at=None;self.watches={}
        self.pending_profile=None
        self.pending_field_setup=None
        self.presence_gap_until=0.;self.presence_gap_trial_id=None
        self.device_identity=None
        self.sequence = self.command_sequence = 0
        self.events = []; self.error = None; self.closed = False; self.closing = False; self.cleanup_confirmed = False
        self.terminal_cleanup = None;self.remote_exit_code = None
        self.close_request_id=None
        self.stop_event = threading.Event()

    def bind_instance(self, binding):
        with self.lock:
            if self.binding is not None and self.binding != binding: raise ValueError('LIVE_REBIND_FORBIDDEN')
            self.binding = checked_binding(binding)

    def start(self, context):
        with self.lock:
            if self.thread is not None: return self.snapshot()
            endpoint = require_adapter(self.binding, operation='observation')
            if not self.identity.is_file() or not self.known_hosts.is_file():
                raise BrokerError('robot_preflight_required', 'Prepare the SSH automation key and trusted host entry in Robots first.', status=409)
            ssh = shutil.which('ssh')
            if not ssh: raise BrokerError('robot_ssh_unavailable', 'OpenSSH client is unavailable.', status=409)
            sha, bundle, digests = reviewed_bundle(self.source_root)
            self.motion_epoch=context.get('motion_epoch')
            self.context = dict(schema='physical-live-start-1.0',
                                **{k:context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                                binding_sha256=self.binding['sha256'], worker_sha256=sha)
            if context.get('source_twin_context') is not None:
                self.context.update(schema='physical-live-start-2.0',
                    source_twin_context=checked_twin_context(context['source_twin_context'],project_id=context['project_id']))
            self.sources = digests
            self.evidence = StreamEvidence(self.archive_root / self.context['operation_id'])
            # Persist the reference before transport. Raw event ID joins do not
            # depend on interpreting a later UI snapshot or exported source time.
            if not self.evidence.append((json.dumps(dict(self.context,worker_sources=digests,schema='physical-live-pc-start-2.0'
                    if self.context['schema'].endswith('2.0') else 'physical-live-pc-start-1.0'),
                    separators=(',',':'),allow_nan=False)+'\n').encode()):
                raise BrokerError('physical_start_recording_failed','Could not record the operation reference.',status=409)
            command = [ssh, '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                       '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none', '-o', 'ForwardAgent=no',
                       '-o', 'ClearAllForwardings=yes', '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none',
                       '-o', 'ConnectTimeout=6', '-o', 'ServerAliveInterval=3', '-o', 'ServerAliveCountMax=2',
                       '-o', 'UserKnownHostsFile=' + str(self.known_hosts), '-i', str(self.identity),
                       '-p', str(endpoint.port), '--', endpoint.user + '@' + endpoint.host,
                       '/bin/bash -c ' + shlex.quote(
                           'set -e; if [ -r /opt/ros/humble/setup.bash ]; then source /opt/ros/humble/setup.bash; fi; '
                           'export ROS_DOMAIN_ID=86 ROS_LOCALHOST_ONLY=1; exec /usr/bin/python3 -u -c ' + shlex.quote(BOOTSTRAP))]
            self.thread = threading.Thread(target=self._run, args=(command, bundle), daemon=True, name='physical-live-session')
            self.thread.start()
            return self.snapshot()

    def _run(self, command, bundle):
        stderr = self.evidence.directory / 'ssh-stderr.log'
        writer = stderr_reader = None
        try:
            with stderr.open('xb') as errors:
                self.process = self.factory(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                def drain_errors():
                    saved=0
                    try:
                        while True:
                            raw=self.process.stderr.read(4096)
                            if not raw:break
                            keep=raw[:max(0,4*1024*1024-saved)]
                            if keep:errors.write(keep);saved+=len(keep)
                            if len(keep)!=len(raw) and not getattr(self,'stderr_truncated',False):
                                self.stderr_truncated=True
                                self.evidence.error=self.evidence.error or 'SSH_STDERR_CAPACITY'
                                self.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
                        errors.flush();os.fsync(errors.fileno())
                    except (OSError,ValueError,BrokerError):
                        self.evidence.error=self.evidence.error or 'SSH_STDERR_RECORDING_FAILED'
                stderr_reader=threading.Thread(target=drain_errors,daemon=True,name='physical-stderr-writer')
                stderr_reader.start()
                def write():
                    try:
                        self.process.stdin.write(bundle)
                        self.process.stdin.write((json.dumps(self.context, separators=(',', ':'))+'\n').encode())
                        self.process.stdin.flush()
                        next_watch=self.clock()
                        while not self.stop_event.is_set():
                            now=self.clock()
                            if now>=next_watch:
                                next_watch=now+.1
                                # Presence is not a movement renewal. The robot
                                # separately expires held input and cancels tasks
                                # after a transport gap without automatic resume.
                                # Check elapsed time on busy AND idle iterations;
                                # a continuous 10Hz gesture must not starve watches.
                                # Enqueue at the tail to preserve command sequence,
                                # while Stop/Close retain replacement admission.
                                with self.lock:
                                    current=(not self.closing and now>=self.presence_gap_until and self.at is not None and 0<=now-self.at<.25
                                             and self.last.get('watch_challenge',self.last.get('challenge')) is not None)
                                    if current:
                                        try:self.command('watch',{},motion_epoch=self.motion_epoch,request_id=uuid4().hex)
                                        except BrokerError as error:
                                            if error.code!='physical_command_buffer':raise
                            try: item = self.writes.get(timeout=max(.001,min(.1,next_watch-self.clock())))
                            except queue.Empty:continue
                            if item is None: break
                            # Expired motor packets never regain life in a blocked OS pipe.
                            if item.get('action') == 'drive' and item['payload']['expires_at_ms'] <= self.wall()*1000: continue
                            if item['action']=='watch' and self.clock()<self.presence_gap_until:continue
                            if item['action']=='watch':
                                with self.lock:
                                    self.watches[item['request_id']]=self.clock()
                                    if len(self.watches)>64:self.watches.pop(next(iter(self.watches)))
                            self.process.stdin.write((json.dumps(item, separators=(',', ':'))+'\n').encode()); self.process.stdin.flush()
                            recorded=deepcopy(item);recorded['payload'].pop('challenge',None);recorded['payload'].pop('watch_challenge',None)
                            recorded.update(schema='physical-live-pc-command-2.0' if item['schema']=='physical-live-command-2.0' else 'physical-live-pc-command-1.0',pc_sent_monotonic_s=self.clock(),
                                            execution_confirmed=False)
                            if not self.evidence.append((json.dumps(recorded,separators=(',',':'),allow_nan=False)+'\n').encode()) and not getattr(self,'recording_pause_sent',False):
                                self.recording_pause_sent=True
                                self.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
                            # Keep stdout open for actual cleanup, but never send
                            # a new presence packet after the explicit Close.
                            if item['action']=='close':break
                    except (OSError, ValueError, BrokerError):
                        with self.lock: self.error = self.error or 'SESSION_PIPE_WRITE_FAILED'
                        self.stop_event.set()
                        try:self.process.stdin.close() # EOF is failure/cleanup, never a success ACK.
                        except (OSError,ValueError):pass
                writer = threading.Thread(target=write, daemon=True, name='physical-live-writer'); writer.start()
                while True:
                    raw = self.process.stdout.readline(MAX_LINE+1)
                    if not raw: break
                    if len(raw) > MAX_LINE or not raw.endswith(b'\n'): raise ValueError('SESSION_EVENT_LINE_LIMIT')
                    event = json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_EVENT')))
                    self.receive(event)
                    archived=deepcopy(event);archived['data'].pop('challenge',None);archived['data'].pop('watch_challenge',None)
                    archived_raw=(json.dumps(archived,separators=(',',':'),allow_nan=False)+'\n').encode()
                    if not self.evidence.append(archived_raw) and not getattr(self,'recording_pause_sent',False):
                        self.recording_pause_sent=True
                        self.command('stop', {}, motion_epoch=uuid4().hex, request_id=uuid4().hex)
                code = self.process.wait(timeout=8)
                stderr_reader.join(timeout=2)
                if stderr_reader.is_alive():self.evidence.error=self.evidence.error or 'SSH_STDERR_FLUSH_PENDING'
                self._classify_remote_exit(code)
        except Exception as error:
            with self.lock: self.error = self.error or type(error).__name__ + ':' + str(error)[:100]
        finally:
            self.stop_event.set()
            process = self.process
            if process:
                try: process.stdin.close()
                except (OSError, ValueError): pass
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
            if writer: writer.join(timeout=1)
            self.evidence.close(cleanup_confirmed=self.cleanup_confirmed)
            with self.lock: self.closed = True

    def _classify_remote_exit(self, code):
        with self.lock:
            self.remote_exit_code=code
            if code or not self.cleanup_confirmed:
                self.error=self.error or ('REMOTE_CLEANUP_REPORTED_INCOMPLETE' if self.terminal_cleanup is not None
                                         else 'REMOTE_EXIT_WITHOUT_CLEANUP')

    def receive(self, event):
        """Identity/freshness boundary; callable by supplementary offline tests."""
        keys = {'schema','operation_id','robot_id','project_id','connection_epoch','sequence','kind','robot_monotonic_s','data'}
        version2=self.context is not None and self.context.get('schema')=='physical-live-start-2.0'
        if version2:keys.add('source_twin_context_id')
        if (not isinstance(event, dict) or set(event) != keys or event['schema'] != ('physical-live-event-2.0' if version2 else SCHEMA)
                or event['kind'] not in {'heartbeat','scan','raw','raw_source','command','cleanup','fault','control_pause'}
                or type(event['sequence']) is not int or not isinstance(event['data'], dict)
                or type(event['robot_monotonic_s']) not in (int, float) or not math.isfinite(event['robot_monotonic_s'])
                or event['robot_monotonic_s'] < 0): raise ValueError('SESSION_EVENT_SHAPE')
        with self.lock:
            if self.closed or any(event[k] != self.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')):
                raise ValueError('SESSION_EVENT_IDENTITY')
            if version2 and event['source_twin_context_id']!=self.context['source_twin_context']['context_id']:
                raise ValueError('SESSION_TWIN_CONTEXT_IDENTITY')
            if event['sequence'] != self.sequence + 1: raise ValueError('SESSION_EVENT_SEQUENCE_GAP')
            self.sequence = event['sequence']
            data = deepcopy(event['data'])
            if event['kind'] == 'heartbeat':
                if data.get('worker_sha256')!=self.context.get('worker_sha256') or not isinstance(data.get('worker_sha256'),str):
                    raise ValueError('SESSION_WORKER_SOURCE_MISMATCH')
                boot,release=data.get('boot_id'),data.get('release_id')
                if not isinstance(boot,str) or not re.fullmatch('[a-f0-9-]{32,36}',boot) or not isinstance(release,str) or not re.fullmatch('[a-f0-9]{64}',release):
                    raise ValueError('SESSION_DEVICE_SOURCE_REQUIRED')
                if self.device_identity is not None and self.device_identity!=(boot,release):raise ValueError('SESSION_BOOT_OR_RELEASE_CHANGED')
                self.device_identity=(boot,release)
                battery=data.get('battery')
                if battery is not None and (not isinstance(battery,dict) or
                    battery.get('voltage_v') is not None and (type(battery['voltage_v']) not in (int,float)
                    or not math.isfinite(battery['voltage_v']) or not 0<=battery['voltage_v']<=50)):
                    raise ValueError('SESSION_BATTERY_SHAPE')
                self.last = data; self.at = self.clock()
                trial=(data.get('field') or {}).get('active_trial') or {}
                if (trial.get('case')=='presence_gap' and trial.get('status')=='RUNNING'
                        and trial.get('publications',0)>0 and trial.get('trial_id')!=self.presence_gap_trial_id):
                    self.presence_gap_trial_id=trial['trial_id'];self.presence_gap_until=self.clock()+.7
                    if self.evidence is not None:
                        gap=dict(schema='physical-live-pc-fault-1.0',operation_id=self.context['operation_id'],
                            trial_id=trial['trial_id'],fault='EXPLICIT_APP_PRESENCE_GAP',duration_s=.7,
                            scope='PC_WATCH_SUPPRESSION_NOT_NETWORK_OUTAGE',pc_monotonic_s=self.clock())
                        if version2:gap.update(project_id=self.context['project_id'],
                            source_twin_context_id=self.context['source_twin_context']['context_id'])
                        self.evidence.append((json.dumps(gap,separators=(',',':'))+'\n').encode())
                battery = data.get('battery')
                if isinstance(battery, dict) and battery.get('source') == 'measured': self.battery_at = self.at
                if not self.closing and self.pending_profile is not None:
                    profile=self.pending_profile
                    self.command('profile',{'profile':profile},motion_epoch=self.motion_epoch,request_id=uuid4().hex)
                    self.pending_profile=None
                if not self.closing and self.pending_field_setup is not None:
                    self.command('field_setup',{'config':self.pending_field_setup},motion_epoch=self.motion_epoch,request_id=uuid4().hex)
                    self.pending_field_setup=None
            elif event['kind'] == 'scan':
                scan = data.get('scan', data)
                points = scan.get('points')
                if (not isinstance(points, list) or len(points) > 8192 or any(not isinstance(p, list) or len(p) != 2
                        or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100 for v in p) for p in points)):
                    raise ValueError('SESSION_SCAN_SHAPE')
                self.scan = scan; self.scan_at=self.clock()
                if version2:
                    self.scan=dict(scan,source_twin_context_id=self.context['source_twin_context']['context_id'],
                        twin_reference_basis='OPERATION_START_REFERENCE_NOT_ACQUISITION_SYNC')
            elif event['kind'] == 'cleanup':
                if data.get('subsystem')=='session':
                    self.terminal_cleanup=deepcopy(data)
                    self.cleanup_confirmed=data.get('confirmed') is True
                if data.get('subsystem')=='session' and data.get('recording_complete') is False and self.evidence is not None:
                    self.evidence.error=self.evidence.error or 'ROBOT_RECORDING_INCOMPLETE'
            elif event['kind']=='command' and data.get('action')=='watch':
                sent=self.watches.pop(data.get('request_id'),None)
                if sent is not None and data.get('status')=='COMPLETED' and 0<=self.clock()-sent<=.5:
                    self.watch_ack_at=self.clock()
            elif event['kind']=='raw_source' and data.get('kind')=='manifest':
                self.source_export=deepcopy(data)
            if event['kind'] not in {'raw','raw_source'}:
                archived=deepcopy(event);archived['data'].pop('challenge',None);archived['data'].pop('watch_challenge',None)
                self.events.append(archived)
                if len(self.events) > 100: del self.events[:-100]

    def command(self, action, payload, *, motion_epoch, request_id, request_twin_context=None):
        if action not in {'lidar','prepare','qualify','drive','task','stop','close','profile','watch',
                          'field_setup','field_arm','field_test','field_review'}:
            raise BrokerError('physical_action_invalid', 'Unsupported physical action.', status=400)
        with self.lock:
            if self.context is None or self.closed:
                raise BrokerError('physical_connection_required', 'Connect this robot first.', status=409)
            if self.closing:
                if action not in {'stop','close'}:
                    raise BrokerError('physical_session_closing', 'Disconnect is already in progress.', status=409)
                # Close includes Stop and is terminal. A later Stop must not
                # replace the queued Close and leave the sensor/session open.
                # Preserve both request identities without claiming a new send
                # or an execution ACK for the coalesced request.
                result=dict(status='accepted',request_id=request_id,operation_id=self.context['operation_id'],
                            coalesced_with_close_request_id=self.close_request_id)
                if self.evidence is not None:
                    admitted=dict(schema='physical-live-pc-admission-1.0',
                        **{k:self.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                        action=action,motion_epoch=motion_epoch,request_id=request_id,
                        disposition='COALESCED_WITH_TERMINAL_CLOSE',close_request_id=self.close_request_id,
                        execution_confirmed=False,pc_monotonic_s=self.clock())
                    self.evidence.append((json.dumps(admitted,separators=(',',':'))+'\n').encode())
                return result
            if action not in {'stop','close'} and (self.at is None or not 0<=self.clock()-self.at<=2.5):
                raise BrokerError('physical_heartbeat_stale', 'The authenticated robot heartbeat is not current.', status=409)
            payload = deepcopy(payload)
            if action in {'drive','task','prepare','qualify','field_arm','field_test'} and self.evidence is not None and self.evidence.error:
                raise BrokerError('physical_recording_incomplete','Recording is incomplete; reconnect after resolving its storage error.',status=409)
            if action == 'drive':
                expires = payload.get('expires_at_ms')
                if type(expires) not in (float,int) or not math.isfinite(expires) or not 0<expires-self.wall()*1000<=300:
                    raise BrokerError('fleet_input_expired', 'Movement input expired; press again.', status=409)
                payload.update(challenge=self.last.get('challenge'), motion_generation=self.last.get('motion_generation'),
                               source_age_ms=max(0,250-(expires-self.wall()*1000)))
            elif action in {'watch','task','qualify','prepare','field_arm','field_test'}:
                payload.update(challenge=self.last.get('watch_challenge',self.last.get('challenge')) if action=='watch' else self.last.get('challenge'),
                    motion_generation=self.last.get('motion_generation'),source_age_ms=0)
            self.command_sequence += 1
            self.motion_epoch=motion_epoch
            packet = dict(schema='physical-live-command-1.0',
                          **{k:self.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                          motion_epoch=motion_epoch,request_id=request_id,sequence=self.command_sequence,action=action,payload=payload)
            if self.context.get('schema')=='physical-live-start-2.0':
                requested=checked_twin_context(request_twin_context,project_id=None if action in {'stop','close'} else self.context['project_id']) if request_twin_context is not None else None
                packet.update(schema='physical-live-command-2.0',source_twin_context_id=self.context['source_twin_context']['context_id'],
                    request_twin_context=requested)
            if action in {'stop','close'}:
                if action=='close':self.closing=True;self.close_request_id=request_id
                # Stop has its own replacement admission, not a full queued drive FIFO.
                try:
                    while True: self.writes.get_nowait()
                except queue.Empty: pass
            try: self.writes.put_nowait(packet)
            except queue.Full:
                raise BrokerError('physical_command_buffer', 'Command channel is congested; no movement was queued.', status=409) from None
            return dict(status='accepted', request_id=request_id, operation_id=self.context['operation_id'])

    def snapshot(self):
        with self.lock:
            age = None if self.at is None else max(0,(self.clock()-self.at)*1000)
            value = deepcopy(self.last)
            if self.closed:
                value['last_reported_lidar_state']=value.get('lidar_state')
                value['lidar_state']='OFF' if self.cleanup_confirmed else 'FAULT'
                value['scan']=None
                diagnostic=value.get('telemetry_diagnostic')
                if isinstance(diagnostic,dict):
                    diagnostic['last_check_values']=deepcopy(diagnostic)
                    diagnostic.update(reason='SESSION_CLOSED_HISTORICAL',source_age_s=None,
                        sensor_receipt_age_s=None,guard_receipt_age_s=None)
            value['robot_recording']=deepcopy(value.get('recording'))
            value['source_export']=deepcopy(getattr(self,'source_export',None))
            verified=self.watch_ack_at is not None and 0<=self.clock()-self.watch_ack_at<2.5
            if self.scan is not None and not self.closed:
                value['scan']=deepcopy(self.scan)
                # Robot acquisition/serial-age metadata is not a PC receipt.
                # Keep unknown timing, completeness and source SHA unchanged.
                value['scan_receipt']=dict(source=self.scan.get('source','physical_native_sensor_unaligned'),
                    age_ms=max(0,(self.clock()-self.scan_at)*1000),age_basis='pc_scan_receipt',
                    frame_id=self.scan.get('frame_id','native_sensor'),
                    aligned=False)
            value.update(connection_state='DISCONNECTED' if self.closed else 'DEGRADED' if self.context is None else 'CONNECTING' if age is None and not self.error else
                         'CONNECTED' if verified and age is not None and age<2500 and not self.error else 'DEGRADED',
                         live_heartbeat=verified and age is not None and age<2500 and not self.closed and not self.error,
                         telemetry_age_ms=age, telemetry_sequence=self.sequence,
                         cleanup_confirmed=self.cleanup_confirmed, transport_error=self.error,
                         terminal_cleanup_received=self.terminal_cleanup is not None,
                         terminal_cleanup=deepcopy(self.terminal_cleanup),remote_exit_code=self.remote_exit_code,
                         recording=self.evidence.snapshot() if self.evidence else None,
                         expected_worker_sha256=self.context.get('worker_sha256') if self.context else None)
            return value

    def close(self):
        with self.lock:
            thread = self.thread
            if thread is None or self.closed: return
        try: self.command('close', {}, motion_epoch=uuid4().hex, request_id=uuid4().hex)
        except BrokerError: pass
        # Give the robot's final STOP, sensor quiet and evidence receipt a chance
        # to arrive. EOF is escalation, never fabricated confirmation.
        thread.join(timeout=30)
        if thread.is_alive():
            self.stop_event.set()
            process = self.process
            if process:
                try: process.stdin.close()
                except (OSError,ValueError): pass
                if process.poll() is None: process.terminate()
            thread.join(timeout=4)
