# SPDX-License-Identifier: Apache-2.0
"""Bounded append-only operation evidence; never performs device operations."""
import json
import hashlib
import time
import sys
from queue import Queue, Empty, Full
from threading import Thread, Lock, Condition
from uuid import uuid4


def _event_json_parts(events,encoder):
    """Canonical list bytes, encoded one admitted event at a time.

    No event identity cache: every submitted value is encoded and hashed anew.
    Avoid both a multi-MB C call and hundreds of thousands of tiny Python
    iterencode fragments for a whole history. Yield between event batches;
    this is background CPU scheduling, not a sensor/control lease extension.
    """
    yield '['
    for index,event in enumerate(events):
        if index:yield encoder.item_separator
        yield encoder.encode(event)
        if (index+1)%32==0:time.sleep(0)
    yield ']'


def materialize_operation(record):
    # Event objects are immutable after admission. Only the list/manifest are
    # captured under the fleet lock; expensive serialization happens outside it.
    digest=hashlib.sha256()
    encoder=json.JSONEncoder(sort_keys=True,ensure_ascii=False,allow_nan=False)
    parts=_event_json_parts(record['events'],encoder) if isinstance(record['events'],list) else encoder.iterencode(record['events'])
    for part in parts:
        digest.update(part.encode('utf-8'))
    record['manifest'].update(event_count=len(record['events']),events_sha256=digest.hexdigest())
    return record


def operation_json_bytes(record,*,separators=None):
    encoder=json.JSONEncoder(ensure_ascii=False,allow_nan=False,separators=separators)
    if not isinstance(record,dict) or not isinstance(record.get('events'),list) or any(type(k) is not str for k in record):
        return b''.join(part.encode('utf-8') for part in encoder.iterencode(record))
    def parts():
        yield '{'
        for index,(key,value) in enumerate(record.items()):
            if index:yield encoder.item_separator
            if key=='events':
                yield encoder.encode(key);yield encoder.key_separator
                yield from _event_json_parts(value,encoder)
            else:
                # Preserve the exact top-level insertion order and encoder
                # key/value spelling without manually reimplementing JSON.
                yield encoder.encode({key:value})[1:-1]
        yield '}'
    return b''.join(part.encode('utf-8') for part in parts())


class FleetRecorder:
    def __init__(self,path):
        self.queue=Queue(1024);self.lock=Lock();self.closed=False
        self.accepted=self.saved=self.bytes=0;self.error=None
        self.stream=path.open('x',encoding='utf-8',newline='\n')
        self.thread=Thread(target=self._write,daemon=True,name='TwinPulseFleetRecorder');self.thread.start()

    def append(self,event):
        content=json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n';size=len(content.encode('utf-8'))
        with self.lock:
            if self.closed or self.error:raise OSError(self.error or 'RECORDING_CLOSED')
            if self.bytes+size>32*1024*1024:self.error='RECORDING_BYTE_CAPACITY';raise OSError(self.error)
            try:self.queue.put_nowait(content)
            except Full:self.error='RECORDING_QUEUE_CAPACITY';raise OSError(self.error)
            self.bytes+=size;self.accepted+=1

    def _write(self):
        try:
            while True:
                try:content=self.queue.get(timeout=.05)
                except Empty:
                    if self.closed:break
                    continue
                try:
                    if self.stream.write(content)!=len(content):raise OSError('SHORT_WRITE')
                    self.stream.flush()
                    with self.lock:self.saved+=1
                finally:self.queue.task_done()
        except Exception:
            with self.lock:self.error='RECORDING_WRITE_FAILED'
        finally:self.stream.close()

    def close(self):
        with self.lock:self.closed=True
        self.thread.join(timeout=1) # Writer needs the lock to commit saved count.
        with self.lock:
            if self.thread.is_alive():self.error=self.error or 'RECORDING_CLOSE_TIMEOUT'
            return dict(accepted=self.accepted,saved=self.saved,error=self.error,
                complete=not self.error and self.accepted==self.saved)


class FleetSnapshotWriter:
    """Coalesce bounded atomic snapshots, never wait for disk on a control lock.

    Append-only events remain the source of crash recovery. An unflushed summary
    is not finalized evidence. One worker preserves write order for each path.
    """
    def __init__(self):
        self.condition=Condition();self.pending={};self.closed=False;self.error=None
        self.failed={};self.failures=0  # per-path last failure; the worker keeps running (2026-10-26)
        self.thread=Thread(target=self._write,daemon=True,name='TwinPulseFleetSnapshots');self.thread.start()

    def submit(self,path,content,*,estimated_bytes=None):
        with self.condition:
            if self.closed:raise OSError('SNAPSHOT_WRITER_CLOSED')
            if self.error and self.error!='SNAPSHOT_WRITE_FAILED':raise OSError(self.error)
            if len(self.pending)>=64 and path not in self.pending:
                self.error='SNAPSHOT_QUEUE_CAPACITY';raise OSError(self.error)
            size=len(content) if isinstance(content,bytes) else estimated_bytes
            if type(size) is not int or size<0:raise ValueError('SNAPSHOT_SIZE_REQUIRED')
            if sum(v[1] for k,v in self.pending.items() if k!=path)+size>64*1024*1024:
                self.error='SNAPSHOT_BYTE_CAPACITY';raise OSError(self.error)
            self.pending[path]=(content,size);self.condition.notify()

    def _write(self):
        observations=0
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.pending or self.closed)
                if not self.pending:break
                path=next(iter(self.pending));content,_=self.pending.pop(path)
            try:
                self._write_one(path,content,observations)
                with self.condition:
                    self.failed.pop(path,None)
                    # One ENOSPC used to kill this thread for the whole session; a later
                    # successful write proves the disk is usable again.
                    if self.error=='SNAPSHOT_WRITE_FAILED':self.error=None
            except Exception as exc:
                with self.condition:self.error='SNAPSHOT_WRITE_FAILED';self.failed[path]=type(exc).__name__;self.failures+=1

    def _write_one(self,path,content,observations):
        if True:
            if True:
                began=time.perf_counter();at_ms=time.time()*1000
                operation_id=content.get('operation_id') if isinstance(content,dict) else None
                events=len(content.get('events',[])) if isinstance(content,dict) else None
                if isinstance(content,dict):
                    materialized=materialize_operation(content)
                    after_materialize=time.perf_counter()
                    content=operation_json_bytes(materialized)
                else:after_materialize=time.perf_counter()
                after_encode=time.perf_counter()
                if len(content)>33*1024*1024:raise OSError('SNAPSHOT_RECORD_CAPACITY')
                path.parent.mkdir(parents=True,exist_ok=True)
                temp=path.with_suffix('.'+uuid4().hex+'.tmp')
                temp.write_bytes(content);temp.replace(path)
                end=time.perf_counter()
                if end-began>.15 and observations<32:
                    observations+=1
                    try:
                        print('TWINPULSE_SNAPSHOT_IO '+json.dumps(dict(operation_id=operation_id,events=events,
                            bytes=len(content),at_ms=at_ms,elapsed_ms=(end-began)*1000,
                            materialize_ms=(after_materialize-began)*1000,encode_ms=(after_encode-after_materialize)*1000,
                            file_ms=(end-after_encode)*1000),separators=(',',':')),file=sys.stderr,flush=True)
                    except Exception:pass

    def close(self):
        with self.condition:self.closed=True;self.condition.notify()
        self.thread.join(timeout=2)
        with self.condition:
            return dict(complete=not self.error and not self.failed and not self.thread.is_alive() and not self.pending,
                        error=self.error or ('SNAPSHOT_CLOSE_TIMEOUT' if self.thread.is_alive() else None),failures=self.failures)
