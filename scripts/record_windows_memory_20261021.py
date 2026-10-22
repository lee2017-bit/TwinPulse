# SPDX-License-Identifier: Apache-2.0
"""Bounded local read-only OS sampler. No process control or product requests.

Working sets can share pages; they must not be summed into physical RAM used.
Private commit is not RAM resident or pagefile bytes. Missing counters stay null.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'

class Performance(c.Structure):
    _fields_=[('cb',w.DWORD)]+[(k,c.c_size_t) for k in ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[(k,w.DWORD) for k in ('HandleCount','ProcessCount','ThreadCount')]
class Memory(c.Structure):
    _fields_=[('cb',w.DWORD),('PageFaultCount',w.DWORD)]+[(k,c.c_size_t) for k in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
class Memory2(c.Structure):
    _fields_=Memory._fields_+[('PrivateWorkingSetSize',c.c_size_t),('SharedCommitUsage',c.c_ulonglong)]
class Process(c.Structure):
    _fields_=[('dwSize',w.DWORD),('cntUsage',w.DWORD),('pid',w.DWORD),('heap',c.c_size_t),('module',w.DWORD),('threads',w.DWORD),('parent_pid',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('name',w.WCHAR*260)]
class Io(c.Structure):
    _fields_=[(k,c.c_ulonglong) for k in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
class Pagefile(c.Structure):
    _fields_=[('cb',w.DWORD),('Reserved',w.DWORD)]+[(k,c.c_size_t) for k in ('TotalSize','TotalInUse','PeakUsage')]

def small(path,limit=131072):
    try:
        if path.is_symlink() or path.stat().st_size>limit:return {}
        value=json.loads(path.read_bytes());return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def classify(rows,binding):
    """PID alone is not parent identity; reject children older than parents."""
    byid={r['pid']:r for r in rows};roles={}
    owner=byid.get(binding.get('owner_pid'))
    if owner and owner.get('created_unix_ms') and owner['name'].lower() in {'twinpulse.exe','python.exe','pythonw.exe'} and abs(owner['created_unix_ms']-binding.get('launch_started_ms',float('inf')))<=10000:
        roles[owner['pid']]='owner'
        for role in ('backend','engine'):
            row=byid.get(binding.get(role+'_pid'))
            if row and row['parent_pid']==owner['pid'] and row.get('created_unix_ms') and row['created_unix_ms']>=owner['created_unix_ms']:roles[row['pid']]=role
    for _ in range(12):
        added=False
        for row in rows:
            parent=byid.get(row['parent_pid'])
            if row['pid'] not in roles and parent and parent['pid'] in roles and row.get('created_unix_ms') and parent.get('created_unix_ms') and row['created_unix_ms']>=parent['created_unix_ms']:
                roles[row['pid']]=roles[parent['pid']]+'_child';added=True
        if not added:break
    for row in rows:
        name=row['name'].lower();row['role']=roles.get(row['pid'],'windows_dwm' if name=='dwm.exe' else 'unattributed_twinpulse' if 'twinpulse' in name else 'other')
    return rows

class Counters:
    def __init__(self):
        self.k=c.WinDLL('kernel32',use_last_error=True);self.p=c.WinDLL('psapi',use_last_error=True)
        for name,args,ret in (
            ('CreateToolhelp32Snapshot',[w.DWORD,w.DWORD],w.HANDLE),('Process32FirstW',[w.HANDLE,c.POINTER(Process)],w.BOOL),('Process32NextW',[w.HANDLE,c.POINTER(Process)],w.BOOL),
            ('OpenProcess',[w.DWORD,w.BOOL,w.DWORD],w.HANDLE),('CloseHandle',[w.HANDLE],w.BOOL),
            ('GetProcessTimes',[w.HANDLE,*([c.POINTER(w.FILETIME)]*4)],w.BOOL),('GetProcessIoCounters',[w.HANDLE,c.POINTER(Io)],w.BOOL),('GetTickCount64',[],c.c_ulonglong)):
            fn=getattr(self.k,name);fn.argtypes=args;fn.restype=ret
        self.p.GetPerformanceInfo.argtypes=[c.POINTER(Performance),w.DWORD];self.p.GetPerformanceInfo.restype=w.BOOL
        self.p.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.c_void_p,w.DWORD];self.p.GetProcessMemoryInfo.restype=w.BOOL
        self.callback=c.WINFUNCTYPE(w.BOOL,c.c_void_p,c.POINTER(Pagefile),w.LPCWSTR)
        self.p.EnumPageFilesW.argtypes=[self.callback,c.c_void_p];self.p.EnumPageFilesW.restype=w.BOOL
    def system(self):
        p=Performance();p.cb=c.sizeof(p)
        if not self.p.GetPerformanceInfo(c.byref(p),p.cb):raise c.WinError(c.get_last_error())
        value={k+'_bytes':int(getattr(p,k)*p.PageSize) for k in ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache','KernelTotal','KernelPaged','KernelNonpaged')}
        value.update(physical_in_use_bytes=value['PhysicalTotal_bytes']-value['PhysicalAvailable_bytes'],page_size_bytes=int(p.PageSize),
            handles=int(p.HandleCount),processes=int(p.ProcessCount),threads=int(p.ThreadCount),uptime_ms=int(self.k.GetTickCount64()))
        pagefiles=[]
        @self.callback
        def collect(_context,info,_name):
            p=info.contents;pagefiles.append({k+'_bytes':int(getattr(p,k)*value['page_size_bytes']) for k in ('TotalSize','TotalInUse','PeakUsage')});return True
        value['pagefiles']=pagefiles if self.p.EnumPageFilesW(collect,None) else None
        return value
    def processes(self):
        rows=[];snap=self.k.CreateToolhelp32Snapshot(2,0)
        if snap==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
        try:
            entry=Process();entry.dwSize=c.sizeof(entry);okay=self.k.Process32FirstW(snap,c.byref(entry))
            while okay:
                row=dict(pid=int(entry.pid),parent_pid=int(entry.parent_pid),name=entry.name,threads=int(entry.threads),created_unix_ms=None,
                    working_set_bytes=None,private_working_set_bytes=None,private_committed_bytes=None,page_fault_count=None)
                handle=self.k.OpenProcess(0x1000|0x10,False,entry.pid) or self.k.OpenProcess(0x1000,False,entry.pid)
                if handle:
                    try:
                        mem=Memory2() if sys.getwindowsversion().build>=19045 else Memory();mem.cb=c.sizeof(mem)
                        okay_memory=self.p.GetProcessMemoryInfo(handle,c.byref(mem),mem.cb)
                        if not okay_memory:
                            mem=Memory();mem.cb=c.sizeof(mem);okay_memory=self.p.GetProcessMemoryInfo(handle,c.byref(mem),mem.cb)
                        if okay_memory:
                            row.update(working_set_bytes=int(mem.WorkingSetSize),private_committed_bytes=int(mem.PrivateUsage),peak_working_set_bytes=int(mem.PeakWorkingSetSize),
                                paged_pool_bytes=int(mem.QuotaPagedPoolUsage),nonpaged_pool_bytes=int(mem.QuotaNonPagedPoolUsage),page_fault_count=int(mem.PageFaultCount),
                                private_working_set_bytes=int(mem.PrivateWorkingSetSize) if isinstance(mem,Memory2) else None)
                        else:row['memory_error']=c.get_last_error()
                        created,exited,kernel,user=(w.FILETIME() for _ in range(4))
                        if self.k.GetProcessTimes(handle,c.byref(created),c.byref(exited),c.byref(kernel),c.byref(user)):
                            ticks=lambda ft:(ft.dwHighDateTime<<32)|ft.dwLowDateTime
                            row.update(created_unix_ms=(ticks(created)-116444736000000000)/10000,cpu_s=(ticks(kernel)+ticks(user))/10000000)
                        io=Io()
                        if self.k.GetProcessIoCounters(handle,c.byref(io)):row['io']={k:int(getattr(io,k)) for k,_ in Io._fields_}
                    finally:self.k.CloseHandle(handle)
                else:row['open_error']=c.get_last_error()
                rows.append(row);okay=self.k.Process32NextW(snap,c.byref(entry))
        finally:self.k.CloseHandle(snap)
        return rows

def binding():
    owner=small(RUNTIME/'launcher.lock');launch=owner.get('launch_id');result={}
    if isinstance(launch,str) and re.fullmatch('[a-f0-9]{32}',launch):
        status=small(RUNTIME/'launches'/launch/'supervisor-status.json')
        result=dict(launch_id=launch,owner_pid=owner.get('owner_pid'),phase=status.get('phase'))
        try:result['launch_started_ms']=datetime.fromisoformat(status['started_at_utc'].replace('Z','+00:00')).timestamp()*1000
        except (KeyError,ValueError):pass
        for role in ('backend','engine'):result[role+'_pid']=(status.get(role) or {}).get('pid')
    active=small(RUNTIME.parent/'installed/active-release.json')
    result.update(release_id=active.get('release_id'),source_sha256=active.get('source_manifest_sha256'))
    return result

def ui_step(log):
    if log is None:return None
    try:
        with log.open('rb') as stream:stream.seek(max(0,log.stat().st_size-65536));lines=stream.read(65536).splitlines()
        for line in reversed(lines):
            try:
                row=json.loads(line)
                if isinstance(row,dict) and isinstance(row.get('ui_step'),str):return dict(name=row['ui_step'][:220],at_ms=row.get('at'))
            except ValueError:pass
    except OSError:pass

def gpu():
    command=shutil.which('nvidia-smi')
    if not command:return dict(status='NOT_AVAILABLE')
    try:
        result=subprocess.run([command,'--query-gpu=index,name,memory.total,memory.used,utilization.gpu,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
        return dict(status='OBSERVED' if result.returncode==0 else 'UNAVAILABLE',csv=result.stdout[:2048],elapsed_scope='Separate low-frequency sample; not per-process VRAM or physical RAM.')
    except Exception as error:return dict(status='UNAVAILABLE',error=type(error).__name__)

def protected_projection(path):
    try:
        with path.open('rb') as stream:stream.seek(max(0,path.stat().st_size-8192));lines=stream.read(8192).splitlines()
        for line in reversed(lines):
            try:return json.loads(line)
            except ValueError:pass
    except OSError:pass
    return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--duration',type=int,default=1800);p.add_argument('--ui-log',type=Path);args=p.parse_args()
    target=args.output.resolve()
    if not target.is_relative_to(OUT.resolve()) or any(x.is_symlink() for x in (target,*target.parents)) or not 3<=args.duration<=2700:raise ValueError('BOUNDED_LOCAL_EVIDENCE_REQUIRED')
    target.mkdir(exist_ok=False);counter=Counters();start=time.monotonic();epoch_ms=time.time()*1000;cpu=time.process_time();rows=0;data_bytes=0
    meta=dict(schema='windows-memory-recording-1.0',created_utc=datetime.now(timezone.utc).isoformat(),recorder_pid=os.getpid(),source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        windows_version=list(sys.getwindowsversion()),cpu_count=os.cpu_count(),
        collector_sources={name:sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in ('record_windows_memory_20261021.py','record_windows_protected_memory_20261021.ps1','capture_windows_memory_detail_20261021.ps1')},
        test_contract_sha256={name:sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in ('verify_robot_focused_journey.ps1','verify_robot_fleet_ui.mjs','verify_robot_lineage_ui.mjs','verify_continuous_reproduction.ps1')},
        system_interval_s=1,all_process_interval_s=5,gpu_interval_s=30,maximum_bytes=64*1024*1024,duration_limit_s=args.duration,
        start_binding=binding(),gpu_initial=gpu(),semantics=['Working set includes shared pages; do not sum it into physical RAM used.',
            'Private commit is not resident RAM or actual pagefile bytes. EX2 private working set is separate; unsupported/denied counters stay null.',
            'SystemCache includes standby pages and overlaps PhysicalAvailable. Kernel pools are not added as disjoint RAM categories.',
            'PageFaultCount includes soft and hard faults; I/O includes non-disk operations. Neither proves disk paging by itself.',
            'Only PID/creation identity, image basename and counters are stored. No command line, environment, keys or window/document content.'])
    (target/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    last_gpu=start;last_step=None;status='DURATION_LIMIT';errors=[];companion=None;companion_log=None
    try:
        companion_log=(target/'protected-recorder.log').open('xb')
        companion=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/record_windows_protected_memory_20261021.ps1'),
            '-OutputDir',str(target),'-Duration',str(args.duration)],stdin=subprocess.DEVNULL,stdout=companion_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        with (target/'samples.jsonl').open('xb') as stream:
            while time.monotonic()-start<args.duration:
                if (target/'stop.request').exists():status='EXPLICIT_END';break
                began=time.monotonic();b=binding();row=dict(index=rows,at_ms=time.time()*1000,monotonic_s=began,elapsed_s=began-start,binding=b,system=counter.system())
                step=ui_step(args.ui_log)
                if step:last_step=step
                row['ui_step']=last_step
                row['protected_process_projection']=protected_projection(target/'protected-processes.jsonl')
                if rows%5==0:row['processes']=classify(counter.processes(),b)
                if rows and began-last_gpu>=30:row['gpu']=gpu();last_gpu=time.monotonic()
                row['sampler_wall_ms']=(time.monotonic()-began)*1000
                raw=(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n').encode();data_bytes+=len(raw)
                if data_bytes>64*1024*1024:status='BYTE_LIMIT';break
                stream.write(raw);stream.flush();rows+=1
                if rows%10==0:os.fsync(stream.fileno())
                time.sleep(max(0.,start+rows-time.monotonic()))
    except Exception as error:status='INCOMPLETE';errors.append(type(error).__name__)
    finally:
        (target/'stop.request').touch(exist_ok=True)
        if companion is not None:
            try:companion.wait(timeout=5)
            except subprocess.TimeoutExpired:
                companion.terminate()
                try:companion.wait(timeout=3)
                except subprocess.TimeoutExpired:errors.append('PROTECTED_SAMPLER_REAP_UNCONFIRMED')
        if companion_log is not None:companion_log.close()
        path=target/'samples.jsonl'
        receipt=dict(status=status,rows=rows,elapsed_s=time.monotonic()-start,recorder_cpu_s=time.process_time()-cpu,errors=errors,
            samples_sha256=sha256(path.read_bytes()).hexdigest() if path.is_file() else None,gpu_final=gpu(),final_binding=binding(),
            protected_recorder_exit_code=companion.returncode if companion is not None else None,
            classification='READ_ONLY_OS_DIAGNOSTICS_NOT_SOLE_CAUSE_OR_USER_ACCEPTANCE')
        (target/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
    return 1 if status=='INCOMPLETE' else 0

if __name__=='__main__':raise SystemExit(main())
