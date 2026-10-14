# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded append-only PC evidence sink; never performs disk I/O on input threads."""
import json
import os
import queue
import threading
import time


class SessionJournal:
    def __init__(self, path, *, capacity=256, sync=os.fsync, max_bytes=8*1024*1024):
        self.path, self.sync = path, sync
        self.queue = queue.Queue(maxsize=capacity)
        self.lock = threading.Lock()
        self.closing = threading.Event()
        self.thread = None
        self.error = None
        self.accepted = self.saved = 0
        self.max_bytes,self.bytes_reserved=max_bytes,0
        self.pending_since = None

    def start(self):
        # Exclusive creation precedes any transport spawn; never overwrite evidence.
        try:stream = self.path.open('xb')
        except OSError:
            with self.lock:self.error = 'JOURNAL_OPEN_FAILED'
            raise
        self.thread = threading.Thread(target=self._write, args=(stream,), daemon=True)
        self.thread.start()

    def append(self, row):
        payload = (json.dumps(row, allow_nan=False, separators=(',', ':'))+'\n').encode('utf-8')
        with self.lock:
            if self.error or self.closing.is_set():
                return False
            if self.bytes_reserved+len(payload)>self.max_bytes:
                self.error='JOURNAL_BYTE_BUDGET'
                return False
            try:
                self.queue.put_nowait(payload)
            except queue.Full:
                self.error = 'JOURNAL_QUEUE_FULL'
                return False
            if self.accepted == self.saved:
                self.pending_since = time.monotonic()
            self.accepted += 1
            self.bytes_reserved+=len(payload)
            return True

    def status(self):
        with self.lock:
            if (not self.error and self.pending_since is not None
                    and time.monotonic()-self.pending_since > 1.):
                self.error = 'JOURNAL_SAVE_STALLED'
            return {'accepted':self.accepted, 'saved':self.saved, 'error':self.error}

    def _write(self, stream):
        try:
            with stream:
                while not self.closing.is_set() or not self.queue.empty():
                    try:
                        batch = [self.queue.get(timeout=.05)]
                    except queue.Empty:
                        continue
                    while len(batch) < 32:
                        try: batch.append(self.queue.get_nowait())
                        except queue.Empty: break
                    stream.write(b''.join(batch))
                    stream.flush()
                    self.sync(stream.fileno())
                    with self.lock:
                        self.saved += len(batch)
                        self.pending_since = time.monotonic() if self.saved < self.accepted else None
        except Exception:
            with self.lock: self.error = 'JOURNAL_WRITE_FAILED'

    def close(self):
        self.closing.set()
        if self.thread:
            self.thread.join(timeout=2.)
        with self.lock:
            if self.thread and self.thread.is_alive(): self.error = 'JOURNAL_CLOSE_TIMEOUT'
        status = self.status()
        return status['error'] is None and status['accepted'] == status['saved']
