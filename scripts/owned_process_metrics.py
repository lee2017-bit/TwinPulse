# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only Windows memory counters for explicitly owned child process trees.

No command lines, environment, process mutation or unrelated process samples.
"""
import ctypes
from ctypes import wintypes
import os


def sample_tree(root_pid):
    if os.name != 'nt':
        raise RuntimeError('WINDOWS_OWNED_METRICS_REQUIRED')
    class Entry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                  ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                  ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                  ('exe',wintypes.WCHAR*260)]
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD),
                  *[(name,ctypes.c_size_t) for name in ('peak_working_set','working_set',
                    'peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessHandleCount.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    snapshot=kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot==ctypes.c_void_p(-1).value:raise OSError('OWNED_PROCESS_SNAPSHOT_FAILED')
    entries={};entry=Entry();entry.size=ctypes.sizeof(entry)
    try:
        success=kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while success:
            entries[entry.pid]=(entry.parent,entry.threads)
            success=kernel.Process32NextW(snapshot,ctypes.byref(entry))
    finally:kernel.CloseHandle(snapshot)
    owned={root_pid}
    while True:
        expanded=owned|{pid for pid,(parent,_) in entries.items() if parent in owned}
        if expanded==owned:break
        owned=expanded
    rows=[]
    for pid in sorted(owned & entries.keys()):
        handle=kernel.OpenProcess(0x1010,False,pid)
        if not handle:continue  # A child can normally exit during sampling.
        try:
            counters=Counters();counters.cb=ctypes.sizeof(counters);handles=wintypes.DWORD()
            if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):
                raise OSError('OWNED_PROCESS_MEMORY_QUERY_FAILED')
            if not kernel.GetProcessHandleCount(handle,ctypes.byref(handles)):
                raise OSError('OWNED_PROCESS_HANDLE_QUERY_FAILED')
            rows.append({'pid':pid,'working_set_bytes':counters.working_set,'private_bytes':counters.private,
                         'handles':handles.value,'threads':entries[pid][1]})
        finally:kernel.CloseHandle(handle)
    return {'root_pid':root_pid,'processes':rows,
            'working_set_bytes':sum(r['working_set_bytes'] for r in rows),
            'private_bytes':sum(r['private_bytes'] for r in rows),
            'handles':sum(r['handles'] for r in rows),'threads':sum(r['threads'] for r in rows)}
