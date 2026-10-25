# SPDX-License-Identifier: Apache-2.0
"""Secret-free elapsed/GC observations, never a request or motion admission gate."""
from collections import deque
from contextlib import contextmanager
import math
import gc
import faulthandler
import json
import re
import sys
from queue import Queue, Empty, Full
from threading import RLock, Event, Thread, get_ident
import time


@contextmanager
def observe_operation_phase(request, name):
    """Optional timing cannot change a result or mask its original exception."""
    began=None
    try:
        if name in {'tp_operation_read','tp_operation_encode','tp_project_catalog'}:
            began=time.perf_counter()
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            if began is not None:
                elapsed=(time.perf_counter()-began)*1000
                if math.isfinite(elapsed):
                    getattr(request,'_twinpulse_latency_phases',{})[name]=max(0,elapsed)
        except Exception:
            pass


class RequestLatencyProbe:
    ROUTES = {'GET /v1/product/viewport', 'GET /v1/product/viewport/current',
              'POST /v1/engine/viewport','GET /v1/product/workflow','GET /v1/product/conversation',
              'GET /v1/product/robot-fleet','POST /v1/product/robot-fleet',
              'GET /v1/product/robot-fleet/operations/:id','GET /v1/product/projects'}

    def __init__(self, *, clock=time.perf_counter, emit=None, dump=None):
        self.clock=clock;self.emit=emit or self._emit
        self.lock=RLock();self.collections=deque(maxlen=32);self.started={}
        self.active=False;self.observations=0
        self.observations_by_route={};self.stacks_by_route={}
        self.route_windows={}
        self.requests={};self.stop_event=Event();self.thread=None
        self.stack_count=0;self.last_stack=-float('inf')
        self.dump=dump or (lambda:faulthandler.dump_traceback(file=sys.stderr,all_threads=True))
        self.records=Queue(maxsize=16);self.writer=None;self.dropped=0

    @staticmethod
    def _emit(value):
        print('TWINPULSE_HTTP_LATENCY '+json.dumps(value,separators=(',',':')),
              file=sys.stderr,flush=True)

    def start(self):
        if not self.active:
            gc.callbacks.append(self._gc);self.active=True
            self.stop_event.clear()
            self.writer=Thread(target=self._write,name='TwinPulseLatencyWriter',daemon=True)
            self.writer.start()
            self.thread=Thread(target=self._watch,name='TwinPulseRequestLatency',daemon=True)
            self.thread.start()

    def stop(self):
        if self.active:
            gc.callbacks.remove(self._gc);self.active=False
            self.stop_event.set();self.thread.join(timeout=.5)
            self.writer.join(timeout=.1)

    def _enqueue(self, value):
        try:self.records.put_nowait(value)
        except Full:self.dropped+=1

    def _write_once(self):
        try:value=self.records.get(timeout=.05)
        except Empty:return
        try:self.emit(value)
        except Exception:pass

    def _write(self):
        while not self.stop_event.is_set():self._write_once()

    def _gc(self, phase, info):
        with self.lock:
            now=self.clock();generation=info['generation']
            if phase=='start':self.started[generation]=now
            elif generation in self.started:
                self.collections.append((self.started.pop(generation),now,generation))

    def begin(self, request):
        for name in ('_twinpulse_latency_started','_twinpulse_latency_phases','_twinpulse_read_id','_twinpulse_latency_route','_twinpulse_error_references','_twinpulse_accepted_at_ms'):
            if hasattr(request,name):delattr(request,name)
        request._tp_probe_sequence=getattr(request,'_tp_probe_sequence',0)+1
        route=request.command+' '+request.path
        if request.command=='GET' and re.fullmatch(r'/v1/product/robot-fleet/operations/[a-f0-9]{32}',request.path):
            # One bounded route bucket, never arbitrary paths/query/body data.
            route='GET /v1/product/robot-fleet/operations/:id'
        if route not in self.ROUTES:return
        request._twinpulse_latency_route=route
        request._twinpulse_latency_started=self.clock()
        request._twinpulse_latency_phases={}
        identity=getattr(request,'headers',{}).get('X-TwinPulse-Read-ID')
        if isinstance(identity,str) and re.fullmatch(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',identity):
            request._twinpulse_read_id=identity
        if getattr(request,'_tp_connection_request_count',request._tp_probe_sequence)==1:
            admission=getattr(getattr(request,'server',None),'request_admission',lambda _:None)(getattr(request,'connection',None))
            if admission and admission[2] is not None:
                accepted,wall,threaded=admission
                request._twinpulse_accepted_at_ms=wall
                request._twinpulse_latency_phases.update(tp_accept_wait=(threaded-accepted)*1000,
                    tp_first_read=(request._twinpulse_latency_started-threaded)*1000)
        with self.lock:self.requests[id(request)]=dict(route=route,began=request._twinpulse_latency_started,
            thread_id=get_ident(),read_id=getattr(request,'_twinpulse_read_id',None),diagnosed=False)

    def _watch_once(self):
        with self.lock:
            now=self.clock()
            for route in {row['route'] for row in self.requests.values()}:
                self._renew_route_window(route,now)
            ready=next((row for row in self.requests.values() if not row['diagnosed'] and now-row['began']>.2
                        and self.stacks_by_route.get(row['route'],0)<2),None)
            if not ready or now-self.last_stack<5:return
            ready['diagnosed']=True;self.last_stack=now;self.stack_count+=1
            self.stacks_by_route[ready['route']]=self.stacks_by_route.get(ready['route'],0)+1
            value=dict(route=ready['route'],blocked_thread_id=ready['thread_id'],
                       read_id=ready['read_id'],elapsed_ms=round((now-ready['began'])*1000,3),at_ms=round(time.time()*1000),kind='pending_stack_no_locals')
        try:self._enqueue(value);self.dump()
        except Exception:pass

    def _watch(self):
        while not self.stop_event.wait(.05):self._watch_once()

    def header(self, request):
        began=getattr(request,'_twinpulse_latency_started',None)
        if began is None:return None
        phases={**request._twinpulse_latency_phases,'tp_handler':(self.clock()-began)*1000}
        return ','.join(name+';dur='+format(max(0,value),'.3f') for name,value in phases.items())

    def finish(self, request):
        began=getattr(request,'_twinpulse_latency_started',None)
        if began is None:return
        end=self.clock()
        with self.lock:self.requests.pop(id(request),None)
        if end-began<.15:return
        with self.lock:
            route=request._twinpulse_latency_route
            self._renew_route_window(route,end)
            if self.observations_by_route.get(route,0)>=16:return
            self.observations+=1
            self.observations_by_route[route]=self.observations_by_route.get(route,0)+1
            collections=[dict(generation=g,elapsed_ms=round((b-a)*1000,3))
                         for a,b,g in self.collections if a<=end and b>=began]
        try:
            self._enqueue(dict(route=route,
                read_id=getattr(request,'_twinpulse_read_id',None),
                at_ms=round(time.time()*1000),elapsed_ms=round((end-began)*1000,3),
                context_id=getattr(request,'_twinpulse_context_id',None),
                project_id=getattr(request,'_twinpulse_project_id',None),
                references={key:value for key,value in getattr(request,'_twinpulse_error_references',{}).items()
                            if key in {'request_id','operation_id'} and isinstance(value,str)
                            and re.fullmatch(r'(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})',value)},
                phases_ms=request._twinpulse_latency_phases,gc=collections))
        except Exception:
            pass  # Optional diagnosis cannot reject a response or renew authority.

    def _renew_route_window(self,route,now):
        # Bound the sink to the existing 16 rows/2 stacks per route, per minute
        # rather than exhausting all future diagnostics during cold startup.
        # Called under self.lock; never sleep, write or affect request admission.
        began=self.route_windows.setdefault(route,now)
        if now-began>=60:
            self.route_windows[route]=now
            self.observations_by_route[route]=0
            self.stacks_by_route[route]=0
