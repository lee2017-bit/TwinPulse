# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Reviewed persistent robot-local stdio endpoint; no action at import time.

Connect starts heartbeat and idle-only board READ. LiDAR and base each require
their explicit action. EOF/signals stop both owners and report observed cleanup.
No shell, model code, client paths, parameter overrides or deployment accepted.
"""
from copy import deepcopy
from twinpulse_core.robot_lineage import checked_twin_context
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import sys
import threading
import time

try:
    from fleet_control import RobotControl, reason_code
    from native_stream import NativeStream
    from robot_journal import RobotJournal
    from teleop_worker import ProtocolOutbox, emit as stdout_emit
except ImportError:
    if __name__=='__main__':
        os.write(2,b'FLEET_WORKER_REJECTED:WORKER_DEPENDENCY_MISSING\n');os._exit(2)
    raise

IDENTITY=('operation_id','robot_id','project_id','connection_epoch')
ACTIONS={'lidar','prepare','qualify','drive','task','watch','stop','close','profile',
         'field_setup','field_arm','field_test','field_review'}
SOURCE_MEMBERS=('heartbeat-board.log','prepare-off.log','prepare-before.log',
    'base.log','final-off.log','final-read.log','qualification.json','field-config.json',
    'field-trials.json','field-stop.json','field-tracking.json','field-commits.jsonl')


def export_sources(directory, emit, *, owners_reaped=True, member_limit=256*1024, total_limit=1024*1024):
    """Export only fixed robot-generated evidence, with explicit truncation.

    Tail chunks preserve exact byte offsets and their own SHA. A whole-source
    SHA is asserted only when every byte was read from a stable regular file.
    There is no client-supplied path, directory traversal or executable input.
    """
    directory=Path(directory);members=[];remaining=total_limit;complete=True
    for name in SOURCE_MEMBERS:
        path=directory/name
        row={'member':name,'status':'NOT_CREATED','source_complete':None}
        try:
            if path.is_symlink():raise ValueError('SOURCE_SYMLINK')
            if not path.exists():
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
        member_limit_bytes=member_limit,total_limit_bytes=total_limit,exported_bytes=total_limit-remaining)
    emit('raw_source',manifest)
    return manifest


def checked_context(value):
    required={'schema',*IDENTITY,'binding_sha256','worker_sha256'}
    version2=isinstance(value,dict) and value.get('schema')=='physical-live-start-2.0'
    if version2:required.add('source_twin_context')
    if not isinstance(value,dict) or set(value)!=required or value['schema'] not in {'physical-live-start-1.0','physical-live-start-2.0'}:
        raise ValueError('START_SHAPE')
    if any(not isinstance(value[k],str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',value[k]) for k in IDENTITY):
        raise ValueError('START_IDENTITY')
    if not re.fullmatch('[a-f0-9]{32}',value['robot_id']):raise ValueError('START_ROBOT_ID')
    if any(not isinstance(value[k],str) or not re.fullmatch('[a-f0-9]{64}',value[k]) for k in ('binding_sha256','worker_sha256')):
        raise ValueError('START_DIGEST')
    if version2:checked_twin_context(value['source_twin_context'],project_id=value['project_id'])
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
    def __init__(self, directory, segment_bytes=4*1024*1024, maximum_bytes=256*1024*1024):
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


class FleetWorker:
    def __init__(self,context,directory,writer,*,clock=time.monotonic,control_factory=RobotControl,native_factory=NativeStream):
        self.context=checked_context(context);self.directory=Path(directory);self.clock=clock
        self.lock=threading.RLock();self.sequence=0;self.last_command=0;self.cancel=threading.Event()
        self.recording_failed=False;self.cleanup_confirmed=False
        self.disk=SegmentedWriter(directory)
        self.journal=RobotJournal(self.directory/'unused',max_bytes=256*1024*1024,capacity=512,
            opener=lambda _:self.disk,buffered=True)
        self.protocol=ProtocolOutbox(writer,max_messages=512,max_bytes=4*1024*1024,buffered=True)
        self.native=native_factory(self.directory/'native',self.emit)
        self.control=control_factory(self.context,self.directory,self.emit,self.native,clock=clock)
        self.board={'voltage_v':None,'source':'unknown','age_ms':None};self.board_at=None
        self.board_lock=threading.Lock();self.board_read_status={'state':'NOT_READ'}
        self.board_thread=None
        self.preparation_challenges={}

    def emit(self,kind,data,*,record=True):
        with self.lock:
            self.sequence+=1
            event=dict(schema='physical-live-event-1.0',**{k:self.context[k] for k in IDENTITY},
                sequence=self.sequence,kind=kind,robot_monotonic_s=self.clock(),data=deepcopy(data))
            if self.context['schema']=='physical-live-start-2.0':
                event.update(schema='physical-live-event-2.0',source_twin_context_id=self.context['source_twin_context']['context_id'])
            archive=deepcopy(event);archive['data'].pop('challenge',None);archive['data'].pop('watch_challenge',None)
            if record:
                try:
                    if self.journal.append(archive) is False:self.recording_failed=True
                except Exception:self.recording_failed=True
            self.protocol.send(event)

    def command(self,value):
        value=checked_command(value,self.context,self.last_command)
        self.last_command=max(self.last_command,value['sequence'])
        action,p=value['action'],value['payload']
        status=self.control.snapshot()
        presence_only=('CLEANUP' if status.get('maintenance_phase')=='CLEANUP' else
                       'PREPARATION' if status['control_state']=='PREPARING' else None)
        if action=='watch' and self.cancel.is_set():raise ValueError('SESSION_CLOSING')
        if action=='watch' and presence_only:
            now=self.clock();issued=self.preparation_challenges.pop(p.get('challenge'),None)
            age=p.get('source_age_ms')
            if (issued is None or type(age) not in (int,float) or not math.isfinite(age)
                    or not 0<=age<250 or not 0<=now-issued+age/1000<.25):
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

    def _idle_board(self):
        from runtime import HOME,ownership,read_board,verify_release
        from robot_health import parse_board_snapshot
        while not self.cancel.is_set():
            if self.control.snapshot()['control_state']=='UNPREPARED':
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
        if status['control_state']=='PREPARING' or status.get('maintenance_phase')=='CLEANUP':
            now=self.clock();self.preparation_challenges={k:v for k,v in self.preparation_challenges.items() if now-v<.25}
            nonce=secrets.token_hex(12);self.preparation_challenges[nonce]=now;status['watch_challenge']=nonce
        if self.recording_failed:
            status['blockers']=status['blockers']+['RECORDING_INCOMPLETE'];status['drive_ready']=False
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
        return dict(status,boot_id=self.context['boot_id'],release_id=self.context['release_id'],sensor_frame=sensor_frame,
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
                except Exception:self.recording_failed=True
                if self.recording_failed:
                    self.control.field_until=0.;self.control.stop_requested.set()
                for _ in range(16):
                    try:value=incoming.messages.get_nowait()
                    except queue.Empty:break
                    try:self.command(value)
                    except Exception as exc:self.emit('fault',{'subsystem':'command','reason':reason_code(exc)})
                if incoming.failed.is_set() and incoming.messages.empty():raise ValueError(incoming.reason)
                if self.clock()-last>=.05:
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
            try:self.emit('cleanup',{'subsystem':'devices','reason':fault,'control':control,'native':native})
            except Exception:pass
            try:
                source_export=export_sources(self.directory,self.emit,owners_reaped=
                    control['worker_reaped'] and not (self.board_thread and self.board_thread.is_alive()))
                if not source_export['complete']:self.recording_failed=True
            except Exception:
                source_export={'complete':False,'reason':'ROBOT_SOURCE_EXPORT_FAILED'};self.recording_failed=True
            journal=self.journal.close(timeout=2.)
            recording_complete=not self.recording_failed and journal['error'] is None and journal['saved']==journal['accepted']
            receipt={'schema':'physical-live-receipt-1.0',**{k:self.context[k] for k in IDENTITY},
                'worker_sha256':self.context['worker_sha256'],'cleanup_confirmed':self.cleanup_confirmed,
                'complete':self.cleanup_confirmed and recording_complete,
                'journal':journal,'segments':self.disk.segments,'reason':fault,'source_export':source_export}
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
                'journal':journal,'source_export':source_export},record=False)
            except Exception:pass
            self.protocol.close(timeout=2.)
        return 0 if self.cleanup_confirmed else 2


def main():
    if sys.argv[1:]:raise ValueError('WORKER_ARGUMENTS_UNSUPPORTED')
    first=sys.stdin.buffer.readline(65537)
    if len(first)>65536 or not first.endswith(b'\n'):raise ValueError('START_LINE_BOUND')
    context=checked_context(json.loads(first))
    if context['worker_sha256']!=os.environ.get('TWINPULSE_FLEET_BUNDLE_SHA256'):raise ValueError('WORKER_BUNDLE_MISMATCH')
    from runtime import HOME,verify_release
    context['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    context['release_id']=verify_release((HOME/'current').resolve(strict=True))['source_id']
    directory=Path.home()/'.local/share/twinpulse/fleet/sessions'/context['operation_id']
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    # Context enrichment is robot-owned, never accepted from PC stdin.
    worker=FleetWorker({k:v for k,v in context.items() if k not in {'boot_id','release_id'}},directory,stdout_emit)
    worker.context.update(boot_id=context['boot_id'],release_id=context['release_id'])
    worker.control.context=worker.context
    for name in ('SIGINT','SIGTERM','SIGHUP'):
        if hasattr(signal,name):signal.signal(getattr(signal,name),lambda *_:worker.cancel.set())
    return worker.run(InputLines(sys.stdin.buffer))


if __name__=='__main__':
    try:result=main()
    except BaseException as exc:
        os.write(2,('FLEET_WORKER_REJECTED:'+reason_code(exc)+'\n').encode())
        result=2
    # The daemon stdin reader may still own a BufferedReader lock after Close.
    # All device owners and evidence have already been finalized by run().
    os._exit(result)
