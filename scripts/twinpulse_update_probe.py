# SPDX-License-Identifier: Apache-2.0
"""Read-only bounded phase diagnostics. No scheduler, deadline or GC tuning."""
import gc
import os
import threading
import time


class UpdateProbe:
    def __init__(self):
        self.thread=threading.get_ident();self.gc_started=None;self.gc_total=0.;self.before_gc=0.;self.before_faults=None
        self._memory=self._memory_reader()
        gc.callbacks.append(self._gc)
    def _gc(self,phase,_info):
        if threading.get_ident()!=self.thread:return
        if phase=='start':self.gc_started=time.monotonic()
        elif self.gc_started is not None:
            self.gc_total+=time.monotonic()-self.gc_started;self.gc_started=None
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
            value=dict(page_fault_count=int(process.PageFaultCount),process_private_mib=process.PrivateUsage/1048576.)
            if kernel.GlobalMemoryStatusEx(c.byref(memory)):value['available_ram_mib']=memory.avail_phys/1048576.
            return value
        return read
    def begin(self):
        self.before_gc=self.gc_total
        self.before_faults=self._memory().get('page_fault_count')
    def finish(self,elapsed):
        result=dict(gc_pause_s=max(0.,self.gc_total-self.before_gc))
        if elapsed>=.25:
            current=self._memory()
            count=current.pop('page_fault_count',None)
            if count is not None and self.before_faults is not None:
                # Windows counts SOFT + HARD faults here. Not a disk-fault claim.
                current['page_fault_delta']=max(0,count-self.before_faults)
            result.update(current)
        return result
    def close(self):
        try:gc.callbacks.remove(self._gc)
        except ValueError:pass
