# SPDX-License-Identifier: Apache-2.0
"""Bounded append-only operation evidence; never performs device operations."""
import json
import hashlib
from queue import Queue, Empty, Full
from threading import Thread, Lock, Condition
from uuid import uuid4


def materialize_operation(record):
    # Event objects are immutable after admission. Only the list/manifest are
    # captured under the fleet lock; expensive serialization happens outside it.
    content=json.dumps(record['events'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')
    record['manifest'].update(event_count=len(record['events']),events_sha256=hashlib.sha256(content).hexdigest())
    return record


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
        self.thread=Thread(target=self._write,daemon=True,name='TwinPulseFleetSnapshots');self.thread.start()

    def submit(self,path,content,*,estimated_bytes=None):
        with self.condition:
            if self.closed or self.error:raise OSError(self.error or 'SNAPSHOT_WRITER_CLOSED')
            if len(self.pending)>=64 and path not in self.pending:
                self.error='SNAPSHOT_QUEUE_CAPACITY';raise OSError(self.error)
            size=len(content) if isinstance(content,bytes) else estimated_bytes
            if type(size) is not int or size<0:raise ValueError('SNAPSHOT_SIZE_REQUIRED')
            if sum(v[1] for k,v in self.pending.items() if k!=path)+size>64*1024*1024:
                self.error='SNAPSHOT_BYTE_CAPACITY';raise OSError(self.error)
            self.pending[path]=(content,size);self.condition.notify()

    def _write(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda:self.pending or self.closed)
                    if not self.pending:break
                    path=next(iter(self.pending));content,_=self.pending.pop(path)
                if isinstance(content,dict):
                    content=json.dumps(materialize_operation(content),ensure_ascii=False,allow_nan=False).encode('utf-8')
                if len(content)>33*1024*1024:raise OSError('SNAPSHOT_RECORD_CAPACITY')
                path.parent.mkdir(parents=True,exist_ok=True)
                temp=path.with_suffix('.'+uuid4().hex+'.tmp')
                temp.write_bytes(content);temp.replace(path)
        except Exception:
            with self.condition:self.error='SNAPSHOT_WRITE_FAILED'

    def close(self):
        with self.condition:self.closed=True;self.condition.notify()
        self.thread.join(timeout=2)
        with self.condition:
            return dict(complete=not self.error and not self.thread.is_alive() and not self.pending,
                        error=self.error or ('SNAPSHOT_CLOSE_TIMEOUT' if self.thread.is_alive() else None))
