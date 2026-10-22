# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded asynchronous robot journal; disk never runs on the control thread."""
import json
import queue
import threading
import time


class RobotJournal:
    def __init__(self, path, *, clock=time.monotonic, capacity=256, max_bytes=64*1024*1024,
                 stall_s=.2, opener=None, buffered=False):
        self.clock, self.stall_s = clock, stall_s
        self.max_bytes = max_bytes; self.reserved = 0
        self.queue = queue.Queue(maxsize=capacity); self.lock = threading.Lock()
        self.pending = {}; self.accepted = self.saved = 0
        self.error = None; self.closed = False; self.max_write_s = 0.
        self.slowest_kind = None
        self.buffered=buffered is True;self.buffering=False;self.oldest_pending_age_s=0.
        # Exclusive creation happens before any device operation.
        self.stream = (opener or (lambda p:p.open('x',encoding='utf-8',newline='\n')))(path)
        self.thread = threading.Thread(target=self._write, daemon=True, name='twinpulse-robot-journal')
        self.thread.start()

    def check(self):
        with self.lock:
            self.oldest_pending_age_s=max(0.,self.clock()-min(self.pending.values())) if self.pending else 0.
            self.buffering=self.oldest_pending_age_s>=self.stall_s
            if self.buffering and not self.buffered:
                self.error = self.error or 'SESSION_JOURNAL_WRITE_STALLED'
            reason = self.error
        if reason: raise ValueError(reason)

    def append(self, event):
        self.append_prepared(json.dumps(event,allow_nan=False)+'\n',event.get('kind'))

    def append_prepared(self,line,kind):
        """Only owned fixed-code JSON; serialization happens before order locks."""
        if not isinstance(line,str) or not line.endswith('\n') or line.count('\n')!=1:
            raise ValueError('SESSION_JOURNAL_PREPARED_LINE')
        size = len(line.encode('utf-8'))
        self.check()
        with self.lock:
            if self.closed: raise ValueError('SESSION_JOURNAL_CLOSED')
            if self.reserved+size > self.max_bytes:
                self.error = self.error or 'SESSION_LOG_BYTE_BUDGET'; raise ValueError(self.error)
            index = self.accepted+1
            self.pending[index] = self.clock()
            try: self.queue.put_nowait((index,line,kind))
            except queue.Full:
                del self.pending[index]
                self.error = self.error or 'SESSION_JOURNAL_QUEUE_FULL'; raise ValueError(self.error)
            self.accepted = index; self.reserved += size

    def _write(self):
        try:
            while True:
                try: index,line,kind = self.queue.get(timeout=.05)
                except queue.Empty:
                    with self.lock:
                        if self.closed: break
                    continue
                started = self.clock()
                try:
                    if self.stream.write(line) != len(line): raise OSError('SHORT_JOURNAL_WRITE')
                    self.stream.flush()
                finally: self.queue.task_done()
                elapsed = self.clock()-started
                with self.lock:
                    if elapsed > self.max_write_s: self.max_write_s,self.slowest_kind = elapsed,kind
                    self.saved += 1; del self.pending[index]
        except Exception:
            with self.lock: self.error = self.error or 'SESSION_JOURNAL_WRITE_FAILED'
        finally:
            try: self.stream.close()
            except Exception:
                with self.lock: self.error = self.error or 'SESSION_JOURNAL_CLOSE_FAILED'

    def status(self):
        with self.lock:
            return {'accepted':self.accepted,'saved':self.saved,'queued':len(self.pending),
                    'error':self.error,'max_write_s':self.max_write_s,
                    'recording_state':'FAILED' if self.error else 'BUFFERING' if self.buffering else 'RECORDING',
                    'oldest_pending_age_s':self.oldest_pending_age_s,
                    'slowest_event_kind':self.slowest_kind,'writer_alive':self.thread.is_alive()}

    def close(self, timeout=1.):
        with self.lock: self.closed = True
        self.thread.join(timeout)
        with self.lock:
            if self.thread.is_alive(): self.error = self.error or 'SESSION_JOURNAL_CLOSE_TIMEOUT'
        return self.status()
