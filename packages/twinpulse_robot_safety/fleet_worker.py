# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Reviewed persistent robot-local stdio endpoint; no action at import time.

Connect starts heartbeat and idle-only board READ. LiDAR and base each require
their explicit action. EOF/signals stop both owners and report observed cleanup.
No shell, model code, client paths, parameter overrides or deployment accepted.
"""
from copy import deepcopy
from control_timing import INPUT_TTL_S, INPUT_TTL_MS
from twinpulse_core.robot_control_timing import EVENT_ARCHIVE_BYTES
from twinpulse_core.robot_lineage import checked_twin_context
from twinpulse_core.robot_timing_profile import checked_profile as checked_timing_profile,values_of,digest as timing_digest
import base64
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import sys
import threading
import time

try:
    from fleet_control import RobotControl, reason_code
    from native_stream import NativeStream
    from robot_journal import RobotJournal
    from teleop_worker import ProtocolOutbox, emit as stdout_emit, emit_line as stdout_emit_line
except ImportError:
    if __name__=='__main__':
        os.write(2,b'FLEET_WORKER_REJECTED:WORKER_DEPENDENCY_MISSING\n');os._exit(2)
    raise

IDENTITY=('operation_id','robot_id','project_id','connection_epoch')
ACTIONS={'lidar','prepare','qualify','drive','task','watch','stop','close','profile',
         'field_setup','field_arm','field_test','field_review'}
SOURCE_MEMBERS=('heartbeat-board.log','output-guard-build.jsonl','output-guard-build.log','prepare-off.log','prepare-before.log',
    'base.log','final-off.log','final-read.log','qualification.json','field-config.json',
    'field-trials.json','field-stop.json','field-tracking.json','field-commits.jsonl')


def export_sources(directory, emit, *, owners_reaped=True, member_limit=256*1024, total_limit=1024*1024,
                   required_members=(),evidence_error=None):
    """Export only fixed robot-generated evidence, with explicit truncation.

    Tail chunks preserve exact byte offsets and their own SHA. A whole-source
    SHA is asserted only when every byte was read from a stable regular file.
    There is no client-supplied path, directory traversal or executable input.
    """
    directory=Path(directory);members=[];remaining=total_limit;complete=evidence_error is None
    for name in SOURCE_MEMBERS:
        path=directory/name
        row={'member':name,'status':'NOT_CREATED','source_complete':None}
        try:
            if path.is_symlink():raise ValueError('SOURCE_SYMLINK')
            if not path.exists():
                if name in required_members:
                    row.update(status='REQUIRED_SOURCE_MISSING',source_complete=False);complete=False
                members.append(row);continue
            if not path.is_file():raise ValueError('SOURCE_NOT_REGULAR')
            before=path.stat();size=before.st_size
            count=min(size,member_limit,remaining);offset=size-count
            with path.open('rb') as stream:
                stream.seek(offset);raw=stream.read(count)
            after=path.stat()
            stable=(before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns and owners_reaped)
            digest=hashlib.sha256(raw).hexdigest()
            full=stable and len(raw)==size and offset==0
            row.update(status='COMPLETE' if full else 'SOURCE_ACTIVE_OR_CHANGED' if not stable else 'TRUNCATED_BUDGET',
                source_size_bytes=size,exported_offset=offset,exported_bytes=len(raw),export_sha256=digest,
                source_sha256=digest if full else None,source_complete=full)
            remaining-=len(raw);complete=complete and full
            for index,start in enumerate(range(0,len(raw),16*1024)):
                chunk=raw[start:start+16*1024]
                emit('raw_source',dict(schema='physical-live-source-1.0',kind='chunk',member=name,
                    source_size_bytes=size,offset=offset+start,length=len(chunk),chunk_index=index,
                    sha256=hashlib.sha256(chunk).hexdigest(),base64=base64.b64encode(chunk).decode()))
        except (OSError,ValueError) as exc:
            row.update(status='EXPORT_FAILED',source_complete=False,reason=reason_code(exc));complete=False
        members.append(row)
    manifest=dict(schema='physical-live-source-1.0',kind='manifest',members=members,complete=complete,
        member_limit_bytes=member_limit,total_limit_bytes=total_limit,exported_bytes=total_limit-remaining,
        evidence_error=evidence_error,required_members=list(required_members))
    emit('raw_source',manifest)
    return manifest


def checked_context(value):
    required={'schema',*IDENTITY,'binding_sha256','worker_sha256'}
    version2=isinstance(value,dict) and value.get('schema')=='physical-live-start-2.0'
    if version2:required.add('source_twin_context')
    if isinstance(value,dict) and 'timing_profile' in value:
        required.update({'timing_profile','timing_profile_sha256'})
    if not isinstance(value,dict) or set(value)!=required or value['schema'] not in {'physical-live-start-1.0','physical-live-start-2.0'}:
        raise ValueError('START_SHAPE')
    if any(not isinstance(value[k],str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',value[k]) for k in IDENTITY):
        raise ValueError('START_IDENTITY')
    if not re.fullmatch('[a-f0-9]{32}',value['robot_id']):raise ValueError('START_ROBOT_ID')
    if any(not isinstance(value[k],str) or not re.fullmatch('[a-f0-9]{64}',value[k]) for k in ('binding_sha256','worker_sha256')):
        raise ValueError('START_DIGEST')
    if version2:checked_twin_context(value['source_twin_context'],project_id=value['project_id'])
    if 'timing_profile' in value:
        checked_timing_profile(value['timing_profile'],robot_id=value['robot_id'],binding_sha256=value['binding_sha256'])
        if timing_digest(value['timing_profile'])!=value['timing_profile_sha256']:raise ValueError('START_TIMING_DIGEST')
    return deepcopy(value)


def checked_command(value, context, last_sequence):
    keys={'schema',*IDENTITY,'motion_epoch','request_id','sequence','action','payload'}
    version2=context.get('schema')=='physical-live-start-2.0'
    if version2:keys.update({'source_twin_context_id','request_twin_context'})
    if (not isinstance(value,dict) or set(value)!=keys or value['schema']!=('physical-live-command-2.0' if version2 else 'physical-live-command-1.0')
            or value['action'] not in ACTIONS or not isinstance(value['payload'],dict)
            or type(value['sequence']) is not int or not 0<value['sequence']<2147483647):
        raise ValueError('COMMAND_SHAPE')
    if any(value[k]!=context[k] for k in IDENTITY):raise ValueError('COMMAND_IDENTITY')
    if version2:
        if value['source_twin_context_id']!=context['source_twin_context']['context_id']:raise ValueError('COMMAND_TWIN_CONTEXT_IDENTITY')
        if value['request_twin_context'] is not None:
            checked_twin_context(value['request_twin_context'],project_id=None if value['action'] in {'stop','close'} else context['project_id'])
    if any(not isinstance(value[k],str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',value[k]) for k in ('request_id','motion_epoch')):
        raise ValueError('COMMAND_IDENTITY')
    if value['action'] not in {'stop','close'} and value['sequence']<=last_sequence:raise ValueError('COMMAND_REPLAY')
    return deepcopy(value)


class InputLines:
    def __init__(self, stream):
        self.stream=stream;self.messages=queue.Queue(maxsize=64);self.failed=threading.Event();self.reason='INPUT_EOF'
        threading.Thread(target=self._read,daemon=True,name='TwinPulseFleetInput').start()

    def _read(self):
        try:
            while True:
                line=self.stream.readline(65537)
                if not line:break
                if len(line)>65536 or not line.endswith(b'\n'):raise ValueError('INPUT_LINE_BOUND')
                value=json.loads(line,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('INPUT_NONFINITE')))
                self.messages.put_nowait(value)
        except Exception as exc:self.reason=reason_code(exc)
        finally:self.failed.set()


class SegmentedWriter:
    """Only the journal's disk thread calls write; hard capacity never drops data."""
    def __init__(self, directory, segment_bytes=4*1024*1024, maximum_bytes=EVENT_ARCHIVE_BYTES):
        self.directory=Path(directory);self.segment_bytes=segment_bytes;self.maximum_bytes=maximum_bytes
        self.total=self.size=0;self.stream=None;self.segments=[];self.digest=None

    def _finish(self):
        if self.stream:
            self.stream.flush();os.fsync(self.stream.fileno());self.stream.close();self.stream=None
            self.segments[-1].update(bytes=self.size,sha256=self.digest.hexdigest())

    def write(self, line):
        data=line.encode('utf-8')
        if self.total+len(data)>self.maximum_bytes:raise OSError('JOURNAL_CAPACITY')
        if self.stream is None or self.size+len(data)>self.segment_bytes:
            self._finish();name='events-%06d.jsonl'%len(self.segments)
            self.stream=(self.directory/name).open('xb');self.segments.append({'path':name});self.size=0;self.digest=hashlib.sha256()
        if self.stream.write(data)!=len(data):raise OSError('JOURNAL_SHORT_WRITE')
        self.size+=len(data);self.total+=len(data);self.digest.update(data)
        return len(line)

    def flush(self):
        if self.stream:self.stream.flush()

    def close(self):self._finish()


SESSION_DISK_RESERVE_BYTES=512*1024*1024  # a session is refused below this free space (phys09: ENOSPC closed the journal mid-run)
SESSION_DISK_FAULT_BYTES=128*1024*1024    # a running session fails closed here, before the writer meets ENOSPC


def session_storage(path=None,usage=shutil.disk_usage):
    """Free bytes on the volume holding the session evidence. Read-only; never prunes."""
    root=Path.home() if path is None else Path(path)
    try:
        free=int(usage(str(root)).free)
        return dict(free_bytes=free,reserve_bytes=SESSION_DISK_RESERVE_BYTES,
                    state='LOW' if free<SESSION_DISK_RESERVE_BYTES else 'OK')
    except OSError as exc:
        return dict(free_bytes=None,reserve_bytes=SESSION_DISK_RESERVE_BYTES,state='UNKNOWN',reason=reason_code(exc))


def rejection_detail(exc):
    """One stderr line for a refused start: reason code plus errno/strerror/path for OSError.

    phys09 (2026-10-26) left only 'FLEET_WORKER_REJECTED:OSError' on the PC while the
    SD card was full; the PC must be able to read the failure class from this line.
    """
    parts=[reason_code(exc)]
    if isinstance(exc,OSError):
        parts.append((errno.errorcode.get(exc.errno) or str(exc.errno)) if exc.errno is not None else 'NO_ERRNO')
        parts.append(str(exc.strerror or '')[:80]);parts.append(str(exc.filename or '')[:160])
    return ':'.join(re.sub(r'[^\x20-\x7e]','?',part) for part in parts)[:300]


def stderr_receipt(line):
    os.write(2,line.encode('utf-8'))


# Liveness and supervision keys travel in every heartbeat. Any other key, and
# any other member of the field block, is omitted while its JSON is
# byte-identical to the previous heartbeat and named in 'unchanged'. Display
# diagnostics are sampled once per HEARTBEAT_SAMPLE_S; a newer value not yet
# sent is named in 'held'. The PC restores both lists from the previous
# heartbeat, and a full heartbeat follows every HEARTBEAT_FULL_S.
HEARTBEAT_EVERY_BEAT=frozenset({'live_heartbeat','control_state','reason','maintenance_phase','blockers','drive_ready','battery','pose',
    'challenge','watch_challenge','motion_generation','applied_motion_epoch','recording_failure_reason','lidar_state','storage','field'})
FIELD_EVERY_BEAT=frozenset({'mode','armed','remaining_s','blockers','active_trial','evidence_error','config_sha256'})
HEARTBEAT_SAMPLED=frozenset({'timing_measurement','telemetry_diagnostic','event_emission','ros_record_delivery','lidar','sensor_frame',
    'motion_observation','recording','field.native_observation'})
HEARTBEAT_SAMPLE_S=1.
HEARTBEAT_FULL_S=30.


def _holdable(key,value,sent):
    """Only counters and ages wait for the sample: what the PC acts on goes out on its own beat."""
    if key not in {'motion_observation','recording'}:return True
    previous=json.loads(sent)
    if not isinstance(value,dict) or not isinstance(previous,dict):return False
    if key=='recording':return all(value.get(k)==previous.get(k) for k in ('error','recording_state','writer_alive'))
    # A wheel observation's start, end or replacement is never held.
    return value.get('state')==previous.get('state')=='OBSERVING' and all(value.get(k)==previous.get(k) for k in ('motion_epoch','request_id','started_s'))


class FleetWorker:
    def __init__(self,context,directory,writer,*,clock=time.monotonic,control_factory=RobotControl,native_factory=NativeStream,line_writer=None,receipt_writer=None):
        self.context=checked_context(context);self.directory=Path(directory);self.clock=clock
        self.lock=threading.RLock();self.sequence=0;self.last_command=0;self.cancel=threading.Event()
        self.recording_failed=False;self.recording_failure_reason=None;self.cleanup_confirmed=False
        self.disk=SegmentedWriter(directory)
        self.journal=RobotJournal(self.directory/'unused',max_bytes=EVENT_ARCHIVE_BYTES,capacity=16384,
            max_pending_bytes=16*1024*1024,
            opener=lambda _:self.disk,buffered=True)
        # 8192 messages / 64 MiB: raw LiDAR chunks are now coalesced (native_stream), and a
        # transient PC stall must not latch PROTOCOL_QUEUE_FULL within seconds (phys09 review).
        # The robot-local journal stays authoritative; motion still pauses on the presence TTL.
        self.protocol=ProtocolOutbox(writer,max_messages=8192,max_bytes=64*1024*1024,buffered=True,line_writer=line_writer)
        self.receipt_writer=receipt_writer or (lambda line:None)
        self.storage_probe=lambda:session_storage(self.directory)
        self.storage=self.storage_probe()
        self.emit_timing=dict(events=0,maximum_payload_prepare_s=0.,maximum_order_lock_wait_s=0.)
        self.native=native_factory(self.directory/'native',self.emit)
        self.control=control_factory(self.context,self.directory,self.emit,self.native,clock=clock)
        self.board={'voltage_v':None,'source':'unknown','age_ms':None};self.board_at=None
        self.board_lock=threading.Lock();self.board_read_status={'state':'NOT_READ'}
        self.board_thread=None
        self.preparation_challenges={}
        self.heartbeat_sent={};self.heartbeat_full_s=self.heartbeat_sample_s=-math.inf;self.recording_fault_reported=False

    def _heartbeat_delta(self,body,now):
        encoded=lambda value:json.dumps(value,allow_nan=False,separators=(',',':'))
        if 'unchanged' in body or 'held' in body:raise ValueError('EVENT_PAYLOAD_SHAPE')
        field=body.get('field');sent=self.heartbeat_sent
        current={k:encoded(v) for k,v in body.items() if k not in HEARTBEAT_EVERY_BEAT}
        if isinstance(field,dict):current.update(('field.'+k,encoded(v)) for k,v in field.items() if k not in FIELD_EVERY_BEAT)
        full=now-self.heartbeat_full_s>=HEARTBEAT_FULL_S;sample=full or now-self.heartbeat_sample_s>=HEARTBEAT_SAMPLE_S
        unchanged=[] if full else [k for k,v in current.items() if sent.get(k)==v]
        value=lambda k:field.get(k[6:]) if k.startswith('field.') else body.get(k)
        held=[] if sample else [k for k,v in current.items() if k in HEARTBEAT_SAMPLED and k in sent and sent[k]!=v and _holdable(k,value(k),sent[k])]
        current.update((k,sent[k]) for k in held)
        if unchanged or held:
            skip={*unchanged,*held}
            body={k:v for k,v in body.items() if k not in skip}
            if isinstance(field,dict):body['field']={k:v for k,v in field.items() if 'field.'+k not in skip}
            if unchanged:body['unchanged']=unchanged
            if held:body['held']=held
        return body,current,(full,sample)

    def emit(self,kind,data,*,record=True):
        if kind=='fault' and isinstance(data,dict) and data.get('subsystem')=='native_archive':
            # A later sensor restart cannot erase an earlier native archive
            # failure in this operation. Existing stop/cancel paths act first.
            self._recording_fault(data.get('reason') or 'NATIVE_ARCHIVE_FAILED')
        # Payloads belong to callers until this owned copy is made. Large
        # heartbeat/raw snapshots and both JSON encodings must NOT hold the
        # order lock needed by the small original input-window/output events.
        began=self.clock()
        try:
            owned=deepcopy(data)
            if not isinstance(owned,dict) or 'event_delivery' in owned:raise ValueError('EVENT_PAYLOAD_SHAPE')
            # Only the run loop emits heartbeats; the delta is committed once the line is sent.
            if kind=='heartbeat':owned,heartbeat_sent,(heartbeat_full,heartbeat_sample)=self._heartbeat_delta(owned,began)
            wire_body=json.dumps(owned,allow_nan=False,separators=(',',':'))
            archive_body=(json.dumps({k:v for k,v in owned.items() if k not in {'challenge','watch_challenge'}},
                allow_nan=False,separators=(',',':')) if record and ('challenge' in owned or 'watch_challenge' in owned) else wire_body)
            if max(len(wire_body.encode('utf-8')),len(archive_body.encode('utf-8')))>256*1024:
                raise ValueError('EVENT_LINE_BYTE_LIMIT')
        except Exception as error:
            self._recording_fault(reason_code(error));raise
        prepared=self.clock()
        with self.lock:
            self.sequence+=1
            enqueued=self.clock()
            event=dict(schema='physical-live-event-1.0',**{k:self.context[k] for k in IDENTITY},
                sequence=self.sequence,kind=kind,robot_monotonic_s=enqueued)
            if self.context['schema']=='physical-live-start-2.0':
                event.update(schema='physical-live-event-2.0',source_twin_context_id=self.context['source_twin_context']['context_id'])
            self.emit_timing['events']+=1
            self.emit_timing['maximum_payload_prepare_s']=max(self.emit_timing['maximum_payload_prepare_s'],prepared-began)
            self.emit_timing['maximum_order_lock_wait_s']=max(self.emit_timing['maximum_order_lock_wait_s'],enqueued-prepared)
            if kind in {'command','control_pause'}:
                diagnostic=json.dumps(dict(schema='robot-event-preparation-1.0',
                    payload_started_s=began,payload_ready_s=prepared,ordered_s=enqueued,
                    payload_prepare_s=prepared-began,order_lock_wait_s=enqueued-prepared),separators=(',',':'))
                # Fixed JSON structure assembly, never string replacement of
                # user text. Nonces and every original source clock are intact.
                def diagnosed(body):return body[:-1]+(',' if body!='{}' else '')+'"event_delivery":'+diagnostic+'}'
                wire_body=diagnosed(wire_body);archive_body=diagnosed(archive_body)
            prefix=json.dumps(event,allow_nan=False,separators=(',',':'))[:-1]+',"data":'
            wire=prefix+wire_body+'}'
            archive=prefix+archive_body+'}\n'
            if max(len(wire.encode('utf-8'))+1,len(archive.encode('utf-8')))>256*1024:
                self._recording_fault('EVENT_LINE_BYTE_LIMIT');raise ValueError('EVENT_LINE_BYTE_LIMIT')
            if record:
                try:
                    if self.journal.append_prepared(archive,kind) is False:self._recording_fault('SESSION_JOURNAL_APPEND_REJECTED')
                except Exception as error:self._recording_fault(reason_code(error))
            try:self.protocol.send_prepared(wire)
            except Exception as error:self._recording_fault(reason_code(error));raise
            if kind=='heartbeat':
                self.heartbeat_sent=heartbeat_sent
                if heartbeat_full:self.heartbeat_full_s=began
                if heartbeat_sample:self.heartbeat_sample_s=began

    def _recording_fault(self,reason='RECORDING_INCOMPLETE'):
        with self.lock:
            first=not self.recording_failed
            self.recording_failed=True
            if first:self.recording_failure_reason=reason
        if not first:return
        control=getattr(self,'control',None)
        if control is not None:
            control.field_until=0.;control.stop_requested.set()
            # Existing cancel checks fence queued/preparing/qualifying paths
            # and every output. End this control owner through its normal
            # zero/OFF finally; do not regenerate Stop events at 100Hz.
            cancel=getattr(control,'cancel',None)
            if cancel is not None:cancel.set()

    def _control_flags(self):
        return self.control.status_flags() if hasattr(self.control,'status_flags') else self.control.snapshot()

    def command(self,value):
        value=checked_command(value,self.context,self.last_command)
        self.last_command=max(self.last_command,value['sequence'])
        action,p=value['action'],value['payload']
        if self.recording_failed and action=='stop':
            self.control.stop_requested.set()
            self.emit('command',dict(request_id=value['request_id'],action='stop',status='REJECTED',
                reason='RECORDING_INCOMPLETE',execution='NOT_EXECUTED_CONTROL_OWNER_CLOSING'))
            return
        if self.recording_failed and action not in {'stop','close','watch'} and not (action=='lidar' and p.get('enabled') is False):
            raise ValueError('RECORDING_INCOMPLETE')
        status=self._control_flags()
        presence_only=('CLEANUP' if status.get('maintenance_phase')=='CLEANUP' else
                       'PREPARATION' if status['control_state']=='PREPARING' else None)
        if action=='watch' and self.cancel.is_set():raise ValueError('SESSION_CLOSING')
        if action=='watch' and presence_only:
            now=self.clock();issued=self.preparation_challenges.pop(p.get('challenge'),None)
            age=p.get('source_age_ms')
            if (issued is None or type(age) not in (int,float) or not math.isfinite(age)
                    or not 0<=age<values_of(self.context.get('timing_profile'))['input_ttl_ms'] or not 0<=now-issued+age/1000<values_of(self.context.get('timing_profile'))['input_ttl_ms']/1000):
                raise ValueError('PREPARATION_PRESENCE_EXPIRED')
            self.emit('command',{'request_id':value['request_id'],'action':'watch','status':'COMPLETED',
                'scope':presence_only+'_PRESENCE_ONLY_NO_MOTION_LEASE'})
            return
        if action=='lidar':
            if set(p)!={'enabled'} or type(p['enabled']) is not bool:raise ValueError('LIDAR_ACTION_SHAPE')
            if p['enabled']:self.native.start()
            else:
                # Sensor Off also pauses current movement; never resumes it.
                self.control.field_until=0.
                self.control.stop_requested.set();self.native.stop()
            self.emit('command',{'request_id':value['request_id'],'action':action,'status':'ACCEPTED',**self.native.snapshot()})
        elif action=='close':self.cancel.set();self.control.submit(value)
        else:self.control.submit(value)

    def _sample_storage(self):
        # Read-only statvfs every idle tick: the heartbeat shows free space before it runs out,
        # and the session fails closed with a named reason instead of a 0-byte manifest.
        storage=self.storage_probe()
        with self.lock:self.storage=storage
        free=storage.get('free_bytes')
        if free is not None and free<SESSION_DISK_FAULT_BYTES:self._recording_fault('SESSION_DISK_LOW')
        return storage

    def _idle_board(self):
        from runtime import HOME,ownership,read_board,verify_release
        from robot_health import parse_board_snapshot
        while not self.cancel.is_set():
            try:self._sample_storage()
            except Exception:pass
            if self._control_flags()['control_state']=='UNPREPARED':
                began=self.clock()
                with self.board_lock:self.board_read_status={'state':'READING','started_s':began}
                try:
                    release=(HOME/'current').resolve(strict=True)
                    if verify_release(release)['source_id']!=self.context['release_id']:raise ValueError('RELEASE_CHANGED')
                    verified=self.clock()
                    with self.board_lock:self.board_read_status={'state':'READING','phase':'BOARD_READ','started_s':began,'release_verify_s':verified-began}
                    with ownership() as lease:
                        path=self.directory/'heartbeat-board.log'
                        offset=path.stat().st_size if path.exists() else 0
                        read_board(release,path,lease.fileno())
                        with path.open('rb') as stream:
                            stream.seek(offset);raw=stream.read(65537)
                        if len(raw)>65536:raise ValueError('BOARD_READ_OUTPUT_BOUND')
                        board=parse_board_snapshot(raw.decode('utf-8'))
                    with self.board_lock:
                        self.board={'voltage_v':board['voltage_v'],'source':'measured','origin':'opencr_idle_read','age_ms':0.}
                        self.board_at=self.clock()
                        self.board_read_status={'state':'OBSERVED','duration_s':self.clock()-began,
                            'release_verify_s':verified-began,'board_read_s':self.clock()-verified}
                except Exception as exc:
                    with self.board_lock:
                        # Preserve the last observation and its original age,
                        # showing read failure explicitly instead of losing it.
                        self.board_read_status={'state':'FAILED','reason':reason_code(exc),'duration_s':self.clock()-began}
            self.cancel.wait(5.)

    def heartbeat(self):
        status=self.control.snapshot()
        # Mapping serialization belongs to the display heartbeat, never the
        # final-output tick or small input-window/Stop publication locks.
        if hasattr(self.control,'task_observation'):status.update(self.control.task_observation(status))
        if status['control_state']=='PREPARING' or status.get('maintenance_phase')=='CLEANUP':
            now=self.clock();self.preparation_challenges={k:v for k,v in self.preparation_challenges.items() if now-v<values_of(self.context.get('timing_profile'))['input_ttl_ms']/1000}
            nonce=secrets.token_hex(12);self.preparation_challenges[nonce]=now;status['watch_challenge']=nonce
        if self.recording_failed:
            status['blockers']=status['blockers']+['RECORDING_INCOMPLETE'];status['drive_ready']=False
            status['recording_failure_reason']=getattr(self,'recording_failure_reason',None)
        battery=status['battery']
        if battery.get('sample_monotonic_s') is not None:
            battery['age_ms']=(self.clock()-battery['sample_monotonic_s'])*1000
        if battery['voltage_v'] is None:
            with self.board_lock:
                battery=deepcopy(self.board)
                if battery['voltage_v'] is not None:battery['age_ms']=(self.clock()-self.board_at)*1000
                battery['read_status']=dict(self.board_read_status)
        frame=self.native.latest_frame()
        sensor_frame=None if frame is None else {'source':'physical_native_sensor_unaligned',
            'age_ms':(self.clock()-frame['timing']['receipt_end_s'])*1000,'age_basis':'serial_receipt',
            'acquisition_timing':frame['timing'],'complete':frame['complete'],'nodes_sha256':frame['nodes_sha256']}
        with self.lock:emission=dict(self.emit_timing);storage=dict(self.storage)
        return dict(status,boot_id=self.context['boot_id'],release_id=self.context['release_id'],sensor_frame=sensor_frame,event_emission=emission,storage=storage,
            worker_sha256=self.context['worker_sha256'],battery=battery,lidar_state=self.native.snapshot()['lidar_state'],lidar=self.native.snapshot(),
            live_heartbeat=True,recording=self.journal.status(),new_integration_hardware_acceptance='NOT_RUN')

    def run(self,incoming):
        self.control.start()
        self.board_thread=threading.Thread(target=self._idle_board,daemon=True,name='TwinPulseIdleRead');self.board_thread.start()
        last=-math.inf;fault=None
        try:
            while not self.cancel.is_set():
                self.protocol.check()
                try:self.journal.check()
                except Exception as error:self._recording_fault(reason_code(error))
                if self.recording_failed and not self.recording_fault_reported:
                    # The owner is revoked without a pause/fault of its own; name the cause once.
                    self.recording_fault_reported=True
                    self.emit('fault',{'subsystem':'recording','reason':self.recording_failure_reason,'recording':self.journal.status()})
                for _ in range(16):
                    try:value=incoming.messages.get_nowait()
                    except queue.Empty:break
                    try:self.command(value)
                    except Exception as exc:self.emit('fault',{'subsystem':'command','reason':reason_code(exc)})
                if incoming.failed.is_set() and incoming.messages.empty():raise ValueError(incoming.reason)
                # Large display/field receipts are not input leases. Keep the
                # preparation/cleanup presence exchange at its original rate;
                # otherwise avoid serializing full receipts at 20Hz alongside
                # the separate 20Hz small input windows.
                with self.control.lock:
                    urgent=(self.control.state['control_state']=='PREPARING'
                            or self.control.state.get('maintenance_phase')=='CLEANUP')
                if self.clock()-last>=(.05 if urgent else .1):
                    self.emit('heartbeat',self.heartbeat());last=self.clock()
                self.cancel.wait(.01)
        except Exception as exc:fault=reason_code(exc)
        finally:
            self.cancel.set();self.control.stop_requested.set()
            # Start both device cleanups immediately; their bounded joins below
            # must not serialize six seconds of sensor drain behind motor exit.
            self.native.stop()
            control=self.control.close();native=self.native.close()
            if self.board_thread:self.board_thread.join(timeout=12)
            # A sensor never started has no rotor-cleanup claim to make.
            native_ok=native['lidar_state']=='OFF'
            control_ok=control['control_state']=='CLOSED' and control['worker_reaped'] and control['cleanup_confirmed']
            self.cleanup_confirmed=control_ok and native_ok and not (self.board_thread and self.board_thread.is_alive())
            try:self.emit('cleanup',{'subsystem':'devices','reason':fault,'control':control,'native':native,
                'recording_failure_reason':self.recording_failure_reason})
            except Exception:pass
            try:
                required=[]
                if control.get('output_guard_diagnostic_expected'):required.append('output-guard-build.jsonl')
                if control.get('output_guard_log_expected'):required.append('output-guard-build.log')
                source_export=export_sources(self.directory,self.emit,owners_reaped=
                    control['worker_reaped'] and not (self.board_thread and self.board_thread.is_alive()),
                    required_members=required,evidence_error=control.get('output_guard_diagnostic_evidence_error'))
                if not source_export['complete']:self._recording_fault(source_export.get('reason','ROBOT_SOURCE_EXPORT_INCOMPLETE'))
            except Exception:
                source_export={'complete':False,'reason':'ROBOT_SOURCE_EXPORT_FAILED'};self._recording_fault('ROBOT_SOURCE_EXPORT_FAILED')
            # Devices are already stopped/reaped. SD-card close/flush is not
            # an output-watchdog deadline: the real 293f3042... session saved
            # every line but its writer was still closing at the former 2 s.
            # Keep this bounded and below the PC's 30 s cleanup join; only an
            # actually reaped writer with exact accepted/saved counts is final.
            journal=self.journal.close(timeout=15.)
            if journal['error'] is not None:self._recording_fault(journal['error'])
            recording_complete=not self.recording_failed and journal['error'] is None and journal['saved']==journal['accepted']
            receipt={'schema':'physical-live-receipt-1.0',**{k:self.context[k] for k in IDENTITY},
                'worker_sha256':self.context['worker_sha256'],'cleanup_confirmed':self.cleanup_confirmed,
                'complete':self.cleanup_confirmed and recording_complete,
                'journal':journal,'segments':self.disk.segments,'reason':fault,'source_export':source_export,
                'recording_failure_reason':self.recording_failure_reason}
            if self.context['schema']=='physical-live-start-2.0':
                receipt['source_twin_context']=deepcopy(self.context['source_twin_context'])
                receipt['twin_reference_basis']='OPERATION_START_REFERENCE_NOT_ACQUISITION_SYNC'
            from runtime import write_json
            try:write_json(self.directory/'receipt.json',receipt)
            except Exception:recording_complete=False
            # Final truth is sent only after disk flush/receipt attempts. This
            # terminal ACK is represented by receipt.json, not appended to a
            # closed journal. A failed recording never becomes PC COMPLETE.
            try:self.emit('cleanup',{'subsystem':'session','confirmed':self.cleanup_confirmed,'reason':fault,
                'control':control,'native':native,'recording_complete':recording_complete,
                'recording_failure_reason':self.recording_failure_reason,
                'journal':journal,'source_export':source_export},record=False)
            except Exception:pass
            # The same verdict on stderr: when the stdout outbox is latched the PC still
            # sees why the worker ended (ssh-stderr.log). Never a PC cleanup confirmation.
            try:self.receipt_writer('FLEET_WORKER_CLEANUP:'+json.dumps(dict(confirmed=self.cleanup_confirmed,reason=fault,
                recording_complete=recording_complete,recording_failure_reason=self.recording_failure_reason,
                control_state=control.get('control_state'),lidar_state=native.get('lidar_state'),
                journal_error=journal.get('error')),allow_nan=False,separators=(',',':'))+'\n')
            except Exception:pass
            self.protocol.close(timeout=2.)
        return 0 if self.cleanup_confirmed else 2


def main():
    if sys.argv[1:]:raise ValueError('WORKER_ARGUMENTS_UNSUPPORTED')
    first=sys.stdin.buffer.readline(65537)
    if len(first)>65536 or not first.endswith(b'\n'):raise ValueError('START_LINE_BOUND')
    context=checked_context(json.loads(first))
    if context['worker_sha256']!=os.environ.get('TWINPULSE_FLEET_BUNDLE_SHA256'):raise ValueError('WORKER_BUNDLE_MISMATCH')
    # Refuse a session on a nearly full SD card before any release, board or device access
    # (phys09: the journal met ENOSPC mid-run and the PC saw only 'OSError').
    storage=session_storage(Path.home())
    if storage['state']=='LOW':
        raise ValueError('SESSION_DISK_LOW_%dMB_FREE'%((storage['free_bytes'] or 0)//(1024*1024)))
    from runtime import HOME,verify_release
    context['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    context['release_id']=verify_release((HOME/'current').resolve(strict=True))['source_id']
    directory=Path.home()/'.local/share/twinpulse/fleet/sessions'/context['operation_id']
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    # Context enrichment is robot-owned, never accepted from PC stdin.
    worker=FleetWorker({k:v for k,v in context.items() if k not in {'boot_id','release_id'}},directory,stdout_emit,line_writer=stdout_emit_line,
        receipt_writer=stderr_receipt)
    worker.context.update(boot_id=context['boot_id'],release_id=context['release_id'])
    worker.control.context=worker.context
    for name in ('SIGINT','SIGTERM','SIGHUP'):
        if hasattr(signal,name):signal.signal(getattr(signal,name),lambda *_:worker.cancel.set())
    return worker.run(InputLines(sys.stdin.buffer))


if __name__=='__main__':
    try:result=main()
    except BaseException as exc:
        os.write(2,('FLEET_WORKER_REJECTED:'+rejection_detail(exc)+'\n').encode())
        result=2
    # The daemon stdin reader may still own a BufferedReader lock after Close.
    # All device owners and evidence have already been finalized by run().
    os._exit(result)
