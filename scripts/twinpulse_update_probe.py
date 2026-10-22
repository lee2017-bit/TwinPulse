# SPDX-License-Identifier: Apache-2.0
"""Read-only bounded phase diagnostics. No scheduler, deadline or GC tuning."""
import gc
import os
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager
from copy import deepcopy


class UpdateProbe:
    def __init__(self,*,record_gc_cycles=False):
        self.thread=threading.get_ident();self.gc_started=None;self.gc_total=0.;self.before_gc=0.;self.before_faults=None
        self.process_gc_started=None;self.process_gc_total=0.;self.phase_worst={}
        self.record_gc_cycles=record_gc_cycles
        self.kit_phase=('between_updates',time.monotonic());self.gc_active=None;self.gc_cycles=deque(maxlen=32)
        self.gc_slow_cycles=deque(maxlen=32);self.gc_completed=0;self.gc_first=None;self.gc_worst=None
        self.gc_unmatched_stops=0;self.gc_incomplete_starts=0
        self._memory=self._memory_reader()
        self.phases=deque(maxlen=64);self.stalls=deque(maxlen=32);self.phase_count=0;self.first_stall=None;self.worst_phase=None;self.diagnostic_errors=0
        gc.callbacks.append(self._gc)

    def _phase_record(self,name,began,elapsed,error=None,extra=None):
        # Fixed code-owned names, original host clocks, bounded memory only.
        # No log/file/HTTP operation is allowed on the measured Kit thread.
        try:
            row=dict(phase=name,entered_monotonic_s=began,ended_monotonic_s=time.monotonic(),
                elapsed_s=elapsed,error_type=error,host_clock='PC_KIT_MONOTONIC_NOT_ROBOT')
            if extra:row.update(extra)
            self.phase_count+=1;self.phases.append(row)
            if elapsed>=.25:
                row.update(self._read_memory())
                self.stalls.append(deepcopy(row))
                if self.first_stall is None:self.first_stall=deepcopy(row)
            if name in self.phase_worst or len(self.phase_worst)<32:
                if name not in self.phase_worst or elapsed>self.phase_worst[name]['elapsed_s']:self.phase_worst[name]=deepcopy(row)
            if self.worst_phase is None or elapsed>self.worst_phase['elapsed_s']:self.worst_phase=deepcopy(row)
        except Exception:self.diagnostic_errors+=1

    def _read_memory(self):
        try:return self._memory()
        except Exception:
            self.diagnostic_errors+=1;return {}

    @contextmanager
    def phase(self,name,*,context=None):
        began=time.monotonic();counter=time.perf_counter();cpu=time.thread_time();before_gc=self.gc_total;before_process_gc=self.process_gc_total;error=None
        is_kit=threading.get_ident()==self.thread;prior_phase=self.kit_phase
        if is_kit:self.kit_phase=(name,began)
        first_count=self.phase_count
        try:yield
        except BaseException as exc:error=type(exc).__name__;raise
        finally:
            try:
                elapsed=time.perf_counter()-counter
                extra=dict(thread_cpu_s=max(0.,time.thread_time()-cpu),gc_pause_s=max(0.,self.gc_total-before_gc),
                    process_gc_pause_s=max(0.,self.process_gc_total-before_process_gc))
                if context is not None:
                    extra['context']=dict(context)
                    if elapsed>=.25:
                        count=min(16,self.phase_count-first_count)
                        extra['child_phases']=deepcopy(list(self.phases)[-count:]) if count else []
                self._phase_record(name,began,elapsed,error,extra=extra)
            except Exception:
                self.diagnostic_errors+=1 # Never mask the original body error/return.
            finally:
                if is_kit:self.kit_phase=prior_phase

    def snapshot(self):
        return dict(schema='kit-phase-ledger-1.0',classification='DIAGNOSTIC_NOT_CONTROL_POLICY',
            phase_count=self.phase_count,retained=len(self.phases),capacity=64,
            first_stall=deepcopy(self.first_stall),worst_phase=deepcopy(self.worst_phase),
            phases=deepcopy(list(self.phases)),recent_stalls=deepcopy(list(self.stalls)),stall_capacity=32,diagnostic_errors=self.diagnostic_errors,
            worst_by_phase=deepcopy(self.phase_worst),
            gc_cycles=dict(enabled=self.record_gc_cycles,completed=self.gc_completed,capacity=32,recent=deepcopy(list(self.gc_cycles)),
                recent_slow=deepcopy(list(self.gc_slow_cycles)),slow_capacity=32,diagnostic_slow_threshold_s=.25,
                first=deepcopy(self.gc_first),worst=deepcopy(self.gc_worst),active=deepcopy(self.gc_active),
                unmatched_stops=self.gc_unmatched_stops,incomplete_starts=self.gc_incomplete_starts,
                scope='Original collector callback interval, not proof all wall time was collector CPU or that a triggering allocation is the root cause. No GC policy change.'),
            page_fault_scope='Windows soft and hard faults combined, not disk-fault attribution')
    @staticmethod
    def _gc_count(info,key):
        value=info.get(key) if isinstance(info,dict) else None
        return value if type(value) is int and 0<=value<=2**63-1 else None

    @staticmethod
    def _gc_stack():
        # Do not retain frames, locals, source text, full paths or argument data.
        rows=[];frame=None
        try:
            frame=sys._getframe(2)
            for _ in range(8):
                if frame is None:break
                code=frame.f_code
                rows.append(dict(file=os.path.basename(code.co_filename.replace('\\','/'))[:120],
                    function=code.co_name[:80],line=frame.f_lineno))
                frame=frame.f_back
        finally:frame=None
        return rows

    def _gc(self,phase,info):
        # GC runs with the process GIL, including callbacks. No locks, I/O,
        # collection requests or scheduling/threshold changes are made here.
        # Keep legacy duration totals even if optional cycle metadata fails.
        try:
            now=time.monotonic();ident=threading.get_ident()
            if phase=='start':
                self.process_gc_started=now
                if ident==self.thread:self.gc_started=now
            elif phase=='stop':
                if self.process_gc_started is not None:
                    self.process_gc_total+=max(0.,now-self.process_gc_started);self.process_gc_started=None
                if ident==self.thread and self.gc_started is not None:
                    self.gc_total+=max(0.,now-self.gc_started);self.gc_started=None
            else:return
        except Exception:
            self.diagnostic_errors+=1;return
        if not self.record_gc_cycles:return
        try:
            if phase=='start':
                began=time.perf_counter()
                if self.gc_active is not None:self.gc_incomplete_starts+=1
                kit_phase=self.kit_phase
                self.gc_active=dict(entered_monotonic_s=now,generation=self._gc_count(info,'generation'),
                    collector_thread_id=ident,collector_thread_name=threading.current_thread().name[:80],
                    collector_is_kit_thread=ident==self.thread,kit_phase_at_start=kit_phase[0],kit_phase_entered_monotonic_s=kit_phase[1],
                    cycle_sequence=self.gc_completed+1,
                    collector_cpu_started_s=self._cpu_sample(time.thread_time),
                    process_cpu_started_s=self._cpu_sample(time.process_time))
                try:self.gc_active['stack']=self._gc_stack()
                except Exception:self.diagnostic_errors+=1;self.gc_active['stack']=[]
                self.gc_active['start_callback_wall_s']=max(0.,time.perf_counter()-began)
            else:
                active=self.gc_active;self.gc_active=None
                if active is None:self.gc_unmatched_stops+=1;return
                generation=self._gc_count(info,'generation')
                paired=ident==active['collector_thread_id'] and generation==active['generation'] and generation in (0,1,2)
                if not paired:self.diagnostic_errors+=1
                row=dict(active,ended_monotonic_s=now,elapsed_s=max(0.,now-active['entered_monotonic_s']),
                    collected=self._gc_count(info,'collected'),uncollectable=self._gc_count(info,'uncollectable'),
                    generation_at_stop=generation,collector_thread_at_stop=ident,
                    pairing='MATCHED' if paired else 'UNKNOWN_OR_MISMATCHED',kit_phase_at_stop=self.kit_phase[0])
                for key,reader,before in (
                    ('collector_thread_cpu_s',time.thread_time,active['collector_cpu_started_s']),
                    ('process_cpu_s',time.process_time,active['process_cpu_started_s'])):
                    current=self._cpu_sample(reader)
                    if current is not None and before is not None and paired:
                        row[key]=max(0.,current-before)
                self.gc_completed+=1;self.gc_cycles.append(row)
                if row['elapsed_s']>=.25:self.gc_slow_cycles.append(row)
                if self.gc_first is None:self.gc_first=row
                if self.gc_worst is None or row['elapsed_s']>self.gc_worst['elapsed_s']:self.gc_worst=row
        except Exception:self.diagnostic_errors+=1
    @staticmethod
    def _memory_reader():
        if os.name!='nt':return lambda:{}
        import ctypes as c
        from ctypes import wintypes as w
        class Process(c.Structure):
            _fields_=[('cb',w.DWORD),('PageFaultCount',w.DWORD)]+[(k,c.c_size_t) for k in
                ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
                 'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
        class Memory(c.Structure):
            _fields_=[('length',w.DWORD),('load',w.DWORD)]+[(k,c.c_ulonglong) for k in
                ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
        kernel=c.WinDLL('kernel32',use_last_error=True);psapi=c.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype=w.HANDLE
        psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Process),w.DWORD]
        handle=kernel.GetCurrentProcess()
        def read():
            process=Process();process.cb=c.sizeof(process);memory=Memory();memory.length=c.sizeof(memory)
            if not psapi.GetProcessMemoryInfo(handle,c.byref(process),process.cb):return {}
            value=dict(page_fault_count=int(process.PageFaultCount),process_private_mib=process.PrivateUsage/1048576.,process_working_set_mib=process.WorkingSetSize/1048576.)
            if kernel.GlobalMemoryStatusEx(c.byref(memory)):value['available_ram_mib']=memory.avail_phys/1048576.
            return value
        return read
    def begin(self):
        self.before_update_phase=self.kit_phase
        self.update_began=time.monotonic()
        self.kit_phase=('app_update',self.update_began)
        self.update_thread_cpu=self._cpu_sample(time.thread_time);self.update_process_cpu=self._cpu_sample(time.process_time)
        self.before_gc=self.gc_total
        self.before_memory=self._read_memory();self.before_faults=self.before_memory.get('page_fault_count')
    def finish(self,elapsed,error=None):
        result={}
        try:
            result['gc_pause_s']=max(0.,self.gc_total-self.before_gc)
            for key,reader,before in (('thread_cpu_s',time.thread_time,self.update_thread_cpu),('process_cpu_s',time.process_time,self.update_process_cpu)):
                current_cpu=self._cpu_sample(reader)
                if current_cpu is not None and before is not None:result[key]=max(0.,current_cpu-before)
            if elapsed>=.25:
                current=self._read_memory()
                count=current.pop('page_fault_count',None)
                if count is not None and self.before_faults is not None:
                    # Windows counts SOFT + HARD faults here. Not a disk-fault claim.
                    current['page_fault_delta']=max(0,count-self.before_faults)
                result.update(current)
                result['before_resources']={k:v for k,v in self.before_memory.items() if k in {'available_ram_mib','process_working_set_mib','process_private_mib'}}
            self._phase_record('app_update',self.update_began,elapsed,error=error,extra=result)
        except Exception:self.diagnostic_errors+=1
        finally:self.kit_phase=self.before_update_phase
        return result
    def _cpu_sample(self,reader):
        try:return reader()
        except Exception:self.diagnostic_errors+=1;return None
    def close(self):
        try:gc.callbacks.remove(self._gc)
        except ValueError:pass
