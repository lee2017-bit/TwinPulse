# SPDX-License-Identifier: Apache-2.0
"""One read-only SIM raycast at a time; no USD, device or control authority.

The result retains the caller's original sample token. There is no waiting job
queue: even a completed but uncollected result occupies the one work slot.
"""
from threading import Condition,Event,Thread
import time


class ScanWorker:
    def __init__(self):
        self.condition=Condition();self.cancel=Event();self.job=None;self.result=None
        self.running=False;self.closed=False;self.thread=None

    def submit(self,token,section,pose):
        with self.condition:
            if self.closed or self.job is not None or self.running or self.result is not None:return False
            self.job=(token,section,tuple(pose))
            if self.thread is None:
                self.thread=Thread(target=self._run,name='TwinPulseSimRaycast',daemon=True)
                self.thread.start()
            self.condition.notify()
            return True

    def poll(self):
        with self.condition:
            result=self.result;self.result=None
            return result

    @property
    def busy(self):
        with self.condition:return self.job is not None or self.running or self.result is not None

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or self.job is not None)
                if self.closed:return
                token,section,pose=self.job;self.job=None;self.running=True
            began=time.monotonic();cpu=time.thread_time();error=None;points=None
            try:points=section.scan(pose,cancel=self.cancel.is_set)
            except Exception as exc:error=str(exc)[:120] if isinstance(exc,ValueError) else type(exc).__name__
            value=dict(token=token,points=points,error=error,started_monotonic_s=began,
                completed_monotonic_s=time.monotonic(),wall_s=time.monotonic()-began,cpu_s=time.thread_time()-cpu)
            with self.condition:
                self.running=False
                if not self.closed:self.result=value

    def close(self):
        self.cancel.set()
        with self.condition:
            self.closed=True;self.job=None;self.result=None;self.condition.notify_all()
        if self.thread:self.thread.join(timeout=1.)
        return dict(closed=True,worker_alive=bool(self.thread and self.thread.is_alive()))
