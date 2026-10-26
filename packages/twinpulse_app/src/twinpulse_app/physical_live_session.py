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
from twinpulse_core.robot_control_timing import INPUT_TTL_S, INPUT_TTL_MS
from twinpulse_core.robot_control_timing import EVENT_ARCHIVE_BYTES
from twinpulse_core.robot_timing_profile import values_of,checked_profile as checked_timing_profile,digest as timing_digest,TimingAccumulator

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
 if not isinstance(name,str): raise ValueError('BOOTSTRAP_PATH')
 flat=re.fullmatch(r'(?:twinpulse_core/)?[a-zA-Z0-9_-][a-zA-Z0-9_.-]*\.(?:py|sh|json)',name)
 guard=re.fullmatch(r'(?:guard_base/(?:src|include)|include/twinpulse_robot_safety)/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-][a-zA-Z0-9_.-]*\.(?:cpp|hpp)',name)
 fixed=name in {'LICENSE.txt','NOTICE.txt','THIRD_PARTY_NOTICES.txt','CMakeLists.txt',
  'guard_base/CMakeLists.txt','guard_base/package.xml','guard_base/LICENSE','guard_base/NOTICE',
  'tests/command_guard_test.cpp','tests/torque_off_test.cpp','tests/ros_guard_test.cpp',
  'tests/fake_include/turtlebot3_node/dynamixel_sdk_wrapper.hpp'}
 if not (flat or guard or fixed): raise ValueError('BOOTSTRAP_PATH')
 if not isinstance(item,dict) or set(item)!={'base64','sha256'}: raise ValueError('BOOTSTRAP_ITEM')
 data=base64.b64decode(item['base64'],validate=True)
 if len(data)>2*1024*1024 or hashlib.sha256(data).hexdigest()!=item['sha256']: raise ValueError('BOOTSTRAP_FILE_SHA')
 decoded[name]=data
digests={k:hashlib.sha256(v).hexdigest() for k,v in decoded.items()}
digest=hashlib.sha256(json.dumps(digests,sort_keys=True,separators=(',',':')).encode()).hexdigest()
if digest!=packet['sha256']: raise ValueError('BOOTSTRAP_BUNDLE_SHA')
root=pathlib.Path.home()/'.local/share/twinpulse/fleet/releases'
if any(p.is_symlink() for p in [root,*root.parents]): raise ValueError('BOOTSTRAP_CACHE_SYMLINK')
root.mkdir(parents=True,exist_ok=True,mode=0o700)
release=root/digest
if release.is_symlink(): raise ValueError('BOOTSTRAP_CACHE_SYMLINK')
release.mkdir(exist_ok=True,mode=0o700)
for name,data in decoded.items():
 path=release/name
 if path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=root): raise ValueError('BOOTSTRAP_MEMBER_SYMLINK')
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
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
             'runtime.py', 'stationary.py', 'owned_exec.py','cleanup_notes.py','control_timing.py','field_config.py','guard_runtime.py')
    files = {}
    guard_paths=[*sorted((package/'guard_base').rglob('*')),
        *sorted((package/'include').rglob('*.hpp')),package/'CMakeLists.txt',
        package/'tests/command_guard_test.cpp',package/'tests/torque_off_test.cpp',package/'tests/ros_guard_test.cpp',
        package/'tests/fake_include/turtlebot3_node/dynamixel_sdk_wrapper.hpp']
    for path in guard_paths:
        if path.is_symlink():raise ValueError('LIVE_GUARD_SOURCE_SYMLINK')
        if path.is_file():files[path.relative_to(package).as_posix()]=path.read_bytes()
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
    pending = ['manual_motion_guard', 'local_navigation', 'ros_observations', 'navigation_binding', 'observation_stream', 'robot_lineage','field_persistence','physical_object_navigation','robot_control_timing','robot_timing_profile','physical_task_observation']
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
    def __init__(self, directory, *, segment_bytes=4*1024*1024, maximum_bytes=EVENT_ARCHIVE_BYTES):
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


def stderr_tail(path,limit=600):
    """Last non-empty ssh stderr lines (e.g. FLEET_WORKER_REJECTED:OSError:ENOSPC:...), bounded, printable."""
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0,os.SEEK_END);size=stream.tell();stream.seek(max(0,size-4096));raw=stream.read()
    except (OSError,ValueError):return None
    lines=[line.strip() for line in raw.decode('utf-8',errors='replace').splitlines() if line.strip()]
    if not lines:return None
    text=' | '.join(lines[-3:])
    text=''.join(ch if 0x20<=ord(ch)<0x7f or ord(ch)>0x9f else '?' for ch in text)
    return text[-limit:]


class PhysicalLiveSession:
    def __init__(self, source_root, archive_root, *, identity, known_hosts,
                 process_factory=subprocess.Popen, clock=time.monotonic, wall=time.time,on_timing_measurement=None):
        self.source_root, self.archive_root = Path(source_root), Path(archive_root)
        self.identity, self.known_hosts = Path(identity), Path(known_hosts)
        self.factory, self.clock, self.wall = process_factory, clock, wall
        self.timing_values=values_of();self.on_timing_measurement=on_timing_measurement
        self.pc_timing_measurements=TimingAccumulator()
        self.lock = threading.RLock(); self.binding = self.context = None
        self.thread = self.process = self.evidence = None
        self.writes = queue.Queue(maxsize=16)
        self.navigation_guard=None
        self.last = {}; self.scan = None; self.scan_at = None; self.at = self.battery_at = None
        self.last_robot_monotonic_s=None;self.command_guards={}
        self.motion_epoch=None
        self.watch_ack_at=None;self.watches={}
        self.input_window=None;self.input_window_at=None;self.input_window_sequence=None;self.queued_at={}
        self.used_input_challenges={};self.pending_drive=None
        self.last_pause_id=None;self.last_robot_pause=None
        self.terminal_motion_observation=None;self.motion_observation_projection_error=None
        self.authority_requested=False
        self.pending_profile=None
        self.pending_field_setup=None
        self.presence_gap_until=0.;self.presence_gap_trial_id=None
        self.device_identity=None
        self.sequence = self.command_sequence = 0
        self.events = []; self.error = None; self.closed = False; self.closing = False; self.cleanup_confirmed = False
        self.terminal_cleanup = None;self.remote_exit_code = None;self.remote_stderr_tail=None
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
            if context.get('timing_profile') is not None:
                configured=checked_timing_profile(context['timing_profile'],robot_id=context['robot_id'],binding_sha256=self.binding['sha256'])
                self.timing_values=values_of(configured)
                self.context.update(timing_profile=configured,timing_profile_sha256=timing_digest(configured))
            self.sources = digests
            self.evidence = StreamEvidence(self.archive_root / self.context['operation_id'])
            # Persist the reference before transport. Raw event ID joins do not
            # depend on interpreting a later UI snapshot or exported source time.
            if not self.evidence.append((json.dumps(dict(self.context,worker_sources=digests,schema='physical-live-pc-start-2.0'
                    if self.context['schema'].endswith('2.0') else 'physical-live-pc-start-1.0'),
                    separators=(',',':'),allow_nan=False)+'\n').encode()):
                raise BrokerError('physical_start_recording_failed','Could not record the operation reference.',status=409)
            # The ordered raw stream repeats large history/diagnostic JSON.
            # SSH's existing lossless transport compression reduces wire bytes
            # without changing a source clock, nonce, event order or admission.
            command = [ssh, '-T', '-C', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                       '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none', '-o', 'ForwardAgent=no',
                       '-o', 'ClearAllForwardings=yes', '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none',
                       # 5 s x 6 = 30 s before ssh gives up: a 7 s home Wi-Fi gap must not end the session
                       # (motion already pauses on the robot's 500 ms presence TTL; phys09 review P0-6).
                       '-o', 'ConnectTimeout=6', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=6', '-o', 'TCPKeepAlive=yes',
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
                                    if self.navigation_guard is not None and not self.navigation_guard():
                                        self.navigation_guard=None
                                        self.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex)
                                    current=(self.input_window is None and not self.closing and now>=self.presence_gap_until and self.at is not None and 0<=now-self.at<self.timing_values['input_ttl_ms']/1000
                                             and self.last.get('watch_challenge',self.last.get('challenge')) is not None)
                                    if current:
                                        try:self.command('watch',{},motion_epoch=self.motion_epoch,request_id=uuid4().hex)
                                        except BrokerError as error:
                                            if error.code!='physical_command_buffer':raise
                            try: item = self.writes.get(timeout=max(.001,min(.1,next_watch-self.clock())))
                            except queue.Empty:continue
                            if item is None: break
                            if not self._claim_task_packet(item):continue
                            # Expired motor packets never regain life in a blocked OS pipe.
                            if item.get('action') == 'drive' and item['payload']['expires_at_ms'] <= self.wall()*1000: continue
                            if item['action']=='watch' and self.clock()<self.presence_gap_until:continue
                            if item['action']=='watch':
                                with self.lock:
                                    self.watches[item['request_id']]=self.clock()
                                    if len(self.watches)>64:self.watches.pop(next(iter(self.watches)))
                            self.process.stdin.write((json.dumps(item, separators=(',', ':'))+'\n').encode()); self.process.stdin.flush()
                            recorded=deepcopy(item);recorded['payload'].pop('challenge',None);recorded['payload'].pop('watch_challenge',None)
                            queued=self.queued_at.pop(item['request_id'],None)
                            recorded['pc_queue_age_s']=self.clock()-queued if queued is not None else None
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
                tail=stderr_tail(stderr)
                with self.lock:self.remote_stderr_tail=tail
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
            measurement=self.last.get('timing_measurement')
            pc_measurement=self.pc_timing_measurements.snapshot()
            if pc_measurement['metrics']:
                measurement=dict(measurement or pc_measurement)
                measurement['metrics']=dict(measurement['metrics'],**pc_measurement['metrics'])
                measurement['duration_s']=max(measurement['duration_s'],pc_measurement['duration_s'])
                measurement['clock_domains']='Per-metric robot clocks or PC monotonic RTT; no PC-minus-robot subtraction'
            if self.on_timing_measurement is not None and measurement is not None:
                for attempt in range(3):
                    try:
                        self.on_timing_measurement(self.context,deepcopy(measurement));break
                    except (ValueError,OSError,KeyError) as exc:
                        if str(exc)=='ROBOT_REGISTRY_BUSY' and attempt<2:
                            time.sleep(.05);continue
                        self.timing_save_error=type(exc).__name__+':'+str(exc)[:100];break
            with self.lock: self.closed = True

    def _classify_remote_exit(self, code):
        # stderr tail (FLEET_WORKER_REJECTED:... / FLEET_WORKER_CLEANUP:...) is attached to link_detail
        # by snapshot(); it is diagnostic text only and never marks cleanup confirmed.
        with self.lock:
            self.remote_exit_code=code
            if code or not self.cleanup_confirmed:
                self.error=self.error or ('REMOTE_CLEANUP_REPORTED_INCOMPLETE' if self.terminal_cleanup is not None
                                         else 'REMOTE_EXIT_WITHOUT_CLEANUP')

    def _observation_identity(self,value,*,terminal=False):
        """Optional display identity only. Never a source of motion authority."""
        if not isinstance(self.context,dict) or not isinstance(value,dict) or value.get('schema')!='robot-wheel-observation-1.0':return None
        if any(value.get(k)!=self.context[k] for k in ('operation_id','robot_id')):return None
        if value.get('source_twin_context_id')!=(self.context.get('source_twin_context') or {}).get('context_id'):return None
        if any(not isinstance(value.get(k),str) or not 1<=len(value[k])<=100 for k in ('motion_epoch','request_id')):return None
        started=value.get('started_s');ended=value.get('ended_s')
        if type(started) not in (int,float) or not 0<=started<1e12 or not math.isfinite(started):return None
        if not isinstance(value.get('state'),str) or value['state'] not in {'OBSERVING','ENDED'}:return None
        if terminal or value['state']=='ENDED':
            if (value['state']!='ENDED' or type(ended) not in (int,float) or not started<=ended<1e12 or not math.isfinite(ended)
                    or value.get('result')!='INCONCLUSIVE_BODY_MOTION' or value.get('body_progress')!='UNKNOWN'):return None
        return (started,value['operation_id'],value['robot_id'],value.get('source_twin_context_id'),value['motion_epoch'],value['request_id'])

    def _retain_terminal_observation(self,event,data):
        candidate=None
        if event['kind']=='control_pause':candidate=data.get('motion_observation')
        elif event['kind']=='command' and data.get('action')=='motion_observation' and data.get('status')=='ENDED':
            candidate=data.get('motion_observation')
        elif event['kind']=='cleanup' and data.get('subsystem') in ('devices','session'):
            control=data.get('control');candidate=control.get('motion_observation') if isinstance(control,dict) else None
        if candidate is None:return
        identity=self._observation_identity(candidate,terminal=True)
        if identity is None or candidate['ended_s']>event['robot_monotonic_s']:
            self.motion_observation_projection_error='INVALID_OPTIONAL_TERMINAL_OBSERVATION';return
        current=self.terminal_motion_observation
        if current is not None:
            prior=current['identity']
            if identity[0]<prior[0] or identity[0]==prior[0] and identity!=prior:return
            if identity==prior and candidate['ended_s']<current['observation']['ended_s']:return
        # data is privately owned before this lock. Capture references only;
        # copying the optional result must not stall Stop/input admission.
        self.terminal_motion_observation=dict(identity=identity,observation=candidate,
            receipt=dict(kind=event['kind'],sequence=event['sequence'],robot_monotonic_s=event['robot_monotonic_s']))

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
        # The reader owns this incoming event. Prepare immutable-to-us copies
        # before the admission lock; display/raw payload size must not pace
        # Stop, held-input admission or the small input-window relay.
        data = deepcopy(event['data'])
        archived = None
        if event['kind'] not in {'raw','raw_source'}:
            archived = dict(event, data={k:v for k,v in data.items() if k not in {'challenge','watch_challenge'}})
        with self.lock:
            if self.closed or any(event[k] != self.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')):
                raise ValueError('SESSION_EVENT_IDENTITY')
            if version2 and event['source_twin_context_id']!=self.context['source_twin_context']['context_id']:
                raise ValueError('SESSION_TWIN_CONTEXT_IDENTITY')
            if event['sequence'] != self.sequence + 1: raise ValueError('SESSION_EVENT_SEQUENCE_GAP')
            self.sequence = event['sequence']
            self._retain_terminal_observation(event,data)
            if event['kind'] == 'heartbeat':
                if data.get('worker_sha256')!=self.context.get('worker_sha256') or not isinstance(data.get('worker_sha256'),str):
                    raise ValueError('SESSION_WORKER_SOURCE_MISMATCH')
                if self.context.get('timing_profile_sha256') is not None and data.get('timing_profile_sha256')!=self.context['timing_profile_sha256']:
                    raise ValueError('SESSION_TIMING_PROFILE_MISMATCH')
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
                self.last = data; self.at = self.clock();self.last_robot_monotonic_s=event['robot_monotonic_s']
                if data.get('control_state')=='PREPARING' or data.get('maintenance_phase')=='CLEANUP':
                    self.input_window=None;self.input_window_at=None
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
                    self.terminal_cleanup=data
                    self.cleanup_confirmed=data.get('confirmed') is True
                if data.get('subsystem')=='session' and data.get('recording_complete') is False and self.evidence is not None:
                    self.evidence.error=self.evidence.error or 'ROBOT_RECORDING_INCOMPLETE'
            elif event['kind']=='control_pause':
                pause_id=data.get('pause_id');reason=data.get('reason')
                if not isinstance(pause_id,str) or not isinstance(reason,str):raise ValueError('CONTROL_PAUSE_SHAPE')
                if pause_id!=self.last_pause_id:
                    self.last_pause_id=pause_id;self.last_robot_pause=data
                    if reason!='OPERATOR_STOP' and not self.closing and (self.authority_requested or self.pending_drive is not None):
                        # A robot-side expiry/fault is an intent fence too.
                        # Never let a still-held old HTTP gesture attach to the
                        # fresh robot nonce generation and resume on its own.
                        request=uuid4().hex
                        self.command('stop',{},motion_epoch=uuid4().hex,request_id=request)
                        self._input_disposition(request,'ROBOT_PAUSE_STOP_FENCE')
            elif event['kind']=='command' and data.get('action')=='input_window':
                issued=data.get('issued_s');generation=data.get('motion_generation')
                if (data.get('schema')!='robot-input-window-1.0'
                        or not isinstance(data.get('challenge'),str) or not re.fullmatch('[a-f0-9]{24}',data['challenge'])
                        or not isinstance(data.get('watch_challenge'),str) or not re.fullmatch('[a-f0-9]{24}',data['watch_challenge'])
                        or type(generation) is not int or generation<0
                        or type(issued) not in (int,float) or not math.isfinite(issued)
                        or not 0<=event['robot_monotonic_s']-issued<self.timing_values['input_ttl_ms']/1000):
                    raise ValueError('INPUT_WINDOW_SHAPE_OR_AGE')
                self.input_window=data;self.input_window_at=self.clock();self.input_window_sequence=event['sequence']
                pending=self.pending_drive
                if pending is not None:
                    self.pending_drive=None
                    valid=(not self.closing and pending['motion_epoch']==self.motion_epoch
                        and pending['generation']==data['motion_generation']
                        and pending['payload']['expires_at_ms']>self.wall()*1000)
                    if valid:
                        self.command('drive',pending['payload'],motion_epoch=pending['motion_epoch'],
                            request_id=pending['request_id'],request_twin_context=pending['request_twin_context'])
                    else:self._input_disposition(pending['request_id'],'DISCARDED_EXPIRED_OR_FENCED')
                # Relay the actual current nonce immediately. Full display/scan
                # updates and the old periodic PC timer do not pace this reply.
                if (not self.closing and self.clock()>=self.presence_gap_until
                        and self.at is not None and 0<=self.clock()-self.at<self.timing_values['input_ttl_ms']/1000):
                    try:self.command('watch',{},motion_epoch=self.motion_epoch,request_id=uuid4().hex)
                    except BrokerError as error:
                        if error.code!='physical_command_buffer':raise
            elif event['kind']=='command' and data.get('action')=='watch':
                sent=self.watches.pop(data.get('request_id'),None)
                if sent is not None:
                    load='tracking_recording' if ((self.last.get('field') or {}).get('tracking') or {}).get('status')=='ESTIMATED' else 'lidar' if self.last.get('lidar_state')=='STREAMING' else 'base'
                    self.pc_timing_measurements.observe('watch_roundtrip_ms',(self.clock()-sent)*1000,self.clock(),load)
                if sent is not None and data.get('status')=='COMPLETED' and 0<=self.clock()-sent<=.5:
                    self.watch_ack_at=self.clock()
            elif event['kind']=='raw_source' and data.get('kind')=='manifest':
                self.source_export=data
            if archived is not None:
                self.events.append(archived)
                if len(self.events) > 100: del self.events[:-100]

    def _input_disposition(self,request_id,disposition):
        if self.evidence is not None:
            value=dict(schema='physical-live-pc-input-disposition-1.0',
                **{k:self.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                request_id=request_id,disposition=disposition,execution_confirmed=False,
                pc_monotonic_s=self.clock())
            self.evidence.append((json.dumps(value,separators=(',',':'))+'\n').encode())

    def command(self, action, payload, *, motion_epoch, request_id, request_twin_context=None, admission_guard=None):
        if action not in {'lidar','prepare','qualify','drive','task','stop','close','profile','watch',
                          'field_setup','field_arm','field_test','field_review'}:
            raise BrokerError('physical_action_invalid', 'Unsupported physical action.', status=400)
        with self.lock:
            if admission_guard is not None and not admission_guard(self.last):
                raise BrokerError('physical_task_revoked','Task context expired before physical queue admission.',status=409)
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
            heartbeat_limit_s=max(2.5,self.timing_values['operator_presence_ms']/1000)
            if action not in {'stop','close'} and (self.at is None or not 0<=self.clock()-self.at<=heartbeat_limit_s):
                raise BrokerError('physical_heartbeat_stale', 'The authenticated robot heartbeat is not current.', status=409)
            if (action in {'drive','task','prepare','qualify','field_arm','field_test'}
                    and motion_epoch!=(self.motion_epoch or self.context.get('motion_epoch'))):
                raise BrokerError('fleet_motion_epoch_changed','The movement generation changed; use a new explicit input.',status=409)
            payload = deepcopy(payload)
            age_checked_s=self.clock();input_age_audit=None
            window=(self.input_window if self.input_window_at is not None
                    and 0<=age_checked_s-self.input_window_at<self.timing_values['input_ttl_ms']/1000 else None)
            if action in {'drive','task','prepare','qualify','field_arm','field_test'} and self.evidence is not None and self.evidence.error:
                raise BrokerError('physical_recording_incomplete','Recording is incomplete; reconnect after resolving its storage error.',status=409)
            if action == 'drive':
                expires = payload.get('expires_at_ms')
                age_checked_wall_s=self.wall()
                if type(expires) not in (float,int) or not math.isfinite(expires) or not 0<expires-age_checked_wall_s*1000<=self.timing_values['input_ttl_ms']:
                    raise BrokerError('fleet_input_expired', 'Movement input expired; press again.', status=409)
                source=window or self.last
                ui_age_ms=max(0,self.timing_values['input_ttl_ms']-(expires-age_checked_wall_s*1000))
                window_age_ms=(age_checked_s-self.input_window_at)*1000 if window else None
                overlap_ms=min(ui_age_ms,window_age_ms) if window_age_ms is not None else 0.
                # The nonce roundtrip already includes PC time since receiving
                # this exact window. Add only UI age before that receipt. The
                # robot-created bound never advances past nonce issuance.
                relay_age_ms=ui_age_ms-overlap_ms
                payload.update(challenge=source.get('challenge'), motion_generation=source.get('motion_generation'),
                               source_age_ms=relay_age_ms)
                input_age_audit=dict(schema='physical-live-pc-input-age-1.0',
                    **{k:self.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                    request_id=request_id,motion_epoch=motion_epoch,motion_generation=source.get('motion_generation'),
                    expires_at_ms=expires,ui_age_ms=ui_age_ms,window_age_ms=window_age_ms,
                    window_received_pc_monotonic_s=self.input_window_at if window else None,
                    window_robot_sequence=self.input_window_sequence if window else None,
                    window_robot_issued_s=source.get('issued_s') if window else None,
                    challenge_fingerprint_sha256=hashlib.sha256(source['challenge'].encode()).hexdigest()
                        if isinstance(source.get('challenge'),str) else None,
                    checked_pc_monotonic_s=age_checked_s,checked_wall_s=age_checked_wall_s,
                    deducted_overlap_ms=overlap_ms,source_age_ms=relay_age_ms,
                    basis='SAME_SMALL_WINDOW_PC_OVERLAP' if window else 'LEGACY_SUM_NO_BOUND_RECEIPT',
                    execution_confirmed=False)
            elif action in {'watch','task','qualify','prepare','field_arm','field_test'}:
                source=window or self.last
                payload.update(challenge=source.get('watch_challenge',source.get('challenge')) if action=='watch' else source.get('challenge'),
                    motion_generation=source.get('motion_generation'),source_age_ms=0)
            token=payload.get('challenge')
            now=self.clock()
            self.used_input_challenges={key:at for key,at in self.used_input_challenges.items() if now-at<2.5}
            if token is not None and token in self.used_input_challenges:
                if action=='drive':
                    if self.pending_drive:self._input_disposition(self.pending_drive['request_id'],'SUPERSEDED_BEFORE_SEND')
                    # At most one held renewal. Wait only within its ORIGINAL
                    # UI expiry and generation; never replay it after Stop/arm.
                    self.pending_drive=dict(payload=payload,motion_epoch=motion_epoch,request_id=request_id,
                        request_twin_context=deepcopy(request_twin_context),generation=payload['motion_generation'])
                    self._input_disposition(request_id,'WAITING_UNUSED_INPUT_WINDOW')
                    return dict(status='pending_input_window',request_id=request_id,operation_id=self.context['operation_id'],execution_confirmed=False)
                if action=='watch':
                    return dict(status='not_sent',request_id=request_id,operation_id=self.context['operation_id'],execution_confirmed=False)
                raise BrokerError('physical_input_window_pending','Wait for a fresh robot input window, then try again.',status=409)
            if action in {'drive','stop','close'} and self.pending_drive is not None:
                self._input_disposition(self.pending_drive['request_id'],'SUPERSEDED_BEFORE_SEND' if action=='drive' else 'DISCARDED_BY_STOP')
                self.pending_drive=None
            if action in {'stop','close'}:self.authority_requested=False
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
                    while True:
                        dropped=self.writes.get_nowait()
                        if isinstance(dropped,dict):self.command_guards.pop(dropped.get('request_id'),None)
                except queue.Empty: pass
            if input_age_audit is not None and self.evidence is not None:
                if not self.evidence.append((json.dumps(input_age_audit,separators=(',',':'),allow_nan=False)+'\n').encode()):
                    raise BrokerError('physical_recording_incomplete','Input-age evidence could not be recorded; no movement was queued.',status=409)
            if admission_guard is not None:self.command_guards[request_id]=admission_guard
            try: self.writes.put_nowait(packet)
            except queue.Full:
                self.command_guards.pop(request_id,None)
                raise BrokerError('physical_command_buffer', 'Command channel is congested; no movement was queued.', status=409) from None
            if token is not None:self.used_input_challenges[token]=now
            # A zero-motion diagnostic deliberately pauses the robot at start.
            # It creates no movement intent for that pause to revoke. Preserve
            # an existing intent/pending drive: do not use collection to clear
            # the fence for a held or queued old gesture.
            motion_field_test=action=='field_test' and payload.get('case') not in {'stationary','soak'}
            if action in {'drive','task','qualify'} or motion_field_test:self.authority_requested=True
            self.queued_at[request_id]=self.clock()
            if len(self.queued_at)>64:self.queued_at.pop(next(iter(self.queued_at)))
            return dict(status='accepted', request_id=request_id, operation_id=self.context['operation_id'])

    def _claim_task_packet(self,packet):
        # Last admission is serialized with Stop/Close queue replacement, but
        # NEVER hold the Stop/state lock across a potentially blocked OS pipe.
        # An admitted in-flight write retains the existing robot nonce/expiry.
        with self.lock:
            guard=self.command_guards.pop(packet['request_id'],None)
            if guard is None:return True
            valid=(not self.closed and not self.closing and packet['motion_epoch']==self.motion_epoch and guard(self.last))
            if not valid:self._input_disposition(packet['request_id'],'TASK_REVOKED_BEFORE_WIRE_ADMISSION')
            return valid

    def snapshot(self):
        with self.lock:
            age = None if self.at is None else max(0,(self.clock()-self.at)*1000)
            # Production receive() replaces privately owned nested reports;
            # capture their references and all scalar state atomically, then
            # copy the large display/history bodies outside admission's lock.
            last,scan=self.last,self.scan
            robot_now=self.last_robot_monotonic_s
            source_export=getattr(self,'source_export',None)
            terminal_cleanup,last_robot_pause=self.terminal_cleanup,self.last_robot_pause
            terminal_observation=self.terminal_motion_observation
            observation_error=self.motion_observation_projection_error
            closed,cleanup_confirmed=self.closed,self.cleanup_confirmed
            evidence=self.evidence
            scan_age=None if self.scan_at is None else max(0,(self.clock()-self.scan_at)*1000)
            heartbeat_limit_ms=max(2500,self.timing_values['operator_presence_ms'])
            verified=self.watch_ack_at is not None and 0<=self.clock()-self.watch_ack_at<heartbeat_limit_ms/1000
            stderr_tail_value=self.remote_stderr_tail
            # Why the link is not CONNECTED, for the operator (display only; admission is unchanged).
            if closed:link_detail=' · '.join(x for x in (self.error,stderr_tail_value) if x) or None
            elif self.context is None:link_detail='no session context'
            elif self.error:link_detail=self.error
            elif age is None:link_detail='waiting for the first heartbeat'
            elif age>=heartbeat_limit_ms:link_detail='no fresh heartbeat for %d ms (limit %d ms)'%(age,heartbeat_limit_ms)
            elif not verified:link_detail='watch round-trip slower than 500 ms or no watch reply within %d ms'%heartbeat_limit_ms
            else:link_detail=None
            recording_failure_reason=last.get('recording_failure_reason') or (terminal_cleanup or {}).get('recording_failure_reason')
            blockers=last.get('blockers') if isinstance(last.get('blockers'),list) else []
            control_owner_state=(None if closed or age is None else
                'EXITED_RECONNECT_REQUIRED' if recording_failure_reason or 'RECORDING_INCOMPLETE' in blockers else 'ACTIVE')
            status=dict(connection_state='DISCONNECTED' if closed else 'DEGRADED' if self.context is None else 'CONNECTING' if age is None and not self.error else
                         'CONNECTED' if verified and age is not None and age<heartbeat_limit_ms and not self.error else 'DEGRADED',
                         link_detail=link_detail,remote_stderr_tail=stderr_tail_value,
                         recording_failure_reason=recording_failure_reason,control_owner_state=control_owner_state,
                         robot_storage=deepcopy(last.get('storage')) if isinstance(last.get('storage'),dict) else None,
                         live_heartbeat=verified and age is not None and age<heartbeat_limit_ms and not closed and not self.error,
                         heartbeat_freshness_ms=heartbeat_limit_ms,
                         telemetry_age_ms=age, telemetry_sequence=self.sequence,
                         cleanup_confirmed=cleanup_confirmed, transport_error=self.error,
                         terminal_cleanup_received=terminal_cleanup is not None,remote_exit_code=self.remote_exit_code,
                         timing_measurement_save_error=getattr(self,'timing_save_error',None),
                         pc_motion_epoch=self.motion_epoch,
                         expected_worker_sha256=self.context.get('worker_sha256') if self.context else None)
        value = deepcopy(last)
        pose_sample=(value.get('pose') or {}).get('sample_s')
        value['pose_age_ms']=(age+max(0.,robot_now-pose_sample)*1000 if age is not None
            and all(type(v) in (int,float) and math.isfinite(v) for v in (robot_now,pose_sample)) and robot_now>=pose_sample else None)
        observation=value.get('motion_observation')
        identity=self._observation_identity(observation) if observation is not None else None
        if observation is not None and identity is None:
            value.pop('motion_observation',None);observation_error=observation_error or 'INVALID_OPTIONAL_HEARTBEAT_OBSERVATION'
        if terminal_observation is not None:
            final=terminal_observation['identity']
            if (identity is None or final[0]>identity[0] or final==identity and
                    (observation.get('state')!='ENDED' or terminal_observation['observation']['ended_s']>=observation['ended_s'])):
                value['motion_observation']=deepcopy(terminal_observation['observation'])
                value['motion_observation_receipt']=deepcopy(terminal_observation['receipt'])
        value['motion_observation_projection_error']=observation_error
        value['last_reported_lidar_state']=value.get('lidar_state')
        value['lidar_state_source']='robot'
        if closed:
            # After an unconfirmed exit the robot never reported FAULT: the PC substitutes it for the
            # drive guard. The source tag lets the UI say "unknown after exit" instead.
            value['lidar_state']='OFF' if cleanup_confirmed else 'FAULT'
            value['lidar_state_source']='pc_after_exit'
            value['scan']=None
            diagnostic=value.get('telemetry_diagnostic')
            if isinstance(diagnostic,dict):
                diagnostic['last_check_values']=deepcopy(diagnostic)
                diagnostic.update(reason='SESSION_CLOSED_HISTORICAL',source_age_s=None,
                    sensor_receipt_age_s=None,guard_receipt_age_s=None)
        task_observation=value.get('task_local_observation') or {}
        ring_end=((task_observation.get('scan') or {}).get('timing') or {}).get('receipt_end_s')
        pose_sample=(task_observation.get('pose') or {}).get('sample_s')
        oldest=min(ring_end,pose_sample) if all(type(v) in (int,float) and math.isfinite(v) for v in (ring_end,pose_sample)) else None
        value['task_observation_age_ms']=(age+max(0.,robot_now-oldest)*1000
            if age is not None and type(robot_now) in (int,float) and oldest is not None and robot_now>=oldest else None)
        value['task_observation_age_basis']='ORIGINAL_RING_AND_ODOM_ROBOT_AGE_PLUS_PC_RECEIPT_ELAPSED_NETWORK_TRANSIT_UNKNOWN'
        value['robot_recording']=deepcopy(value.get('recording'))
        value['source_export']=deepcopy(source_export)
        if scan is not None and not closed:
            value['scan']=deepcopy(scan)
            # Robot acquisition/serial-age metadata is not a PC receipt.
            # Keep unknown timing, completeness and source SHA unchanged.
            value['scan_receipt']=dict(source=scan.get('source','physical_native_sensor_unaligned'),
                age_ms=scan_age,age_basis='pc_scan_receipt',
                frame_id=scan.get('frame_id','native_sensor'),
                aligned=False)
        value.update(status,terminal_cleanup=deepcopy(terminal_cleanup),last_robot_pause=deepcopy(last_robot_pause),
            recording=evidence.snapshot() if evidence else None)
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
