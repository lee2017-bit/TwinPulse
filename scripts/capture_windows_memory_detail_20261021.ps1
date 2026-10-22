# SPDX-License-Identifier: Apache-2.0
# Once-per-stage WMI/GPU detail; never run in the held-control latency window.
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $Output){throw 'New evidence required'}
$tpTime=[Diagnostics.Stopwatch]::StartNew()
$tpErrors=@();$tpGpu=@();$tpGpuProcess=@();$tpMemory=$null
try{$tpMemory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory | Select-Object AvailableMBytes,CommittedBytes,CommitLimit,CacheBytes,PoolPagedBytes,PoolNonpagedBytes,PageReadsPersec,PagesInputPersec,ModifiedPageListBytes,StandbyCacheNormalPriorityBytes,StandbyCacheReserveBytes,StandbyCacheCoreBytes,FreeAndZeroPageListBytes}catch{$tpErrors+='MEMORY_'+$_.Exception.GetType().Name}
try{$tpGpu=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory | Select-Object Name,DedicatedUsage,SharedUsage,TotalCommitted)}catch{$tpErrors+='GPU_ADAPTER_'+$_.Exception.GetType().Name}
try{$tpGpuProcess=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Select-Object Name,DedicatedUsage,SharedUsage,TotalCommitted)}catch{$tpErrors+='GPU_PROCESS_'+$_.Exception.GetType().Name}
$tpRows=@(Get-Process | ForEach-Object {[ordered]@{pid=$_.Id;name=$_.ProcessName;working_set_bytes=$_.WorkingSet64;private_committed_bytes=$_.PrivateMemorySize64;handles=$_.HandleCount}})
$tpOs=Get-CimInstance Win32_OperatingSystem
$tpValue=[ordered]@{schema='windows-memory-stage-detail-1.0';at_utc=[DateTime]::UtcNow.ToString('o');last_boot=$tpOs.LastBootUpTime.ToString('o');
 memory=$tpMemory;gpu_adapters=$tpGpu;gpu_processes=$tpGpuProcess;processes=$tpRows;errors=$tpErrors;sampler_wall_ms=$tpTime.Elapsed.TotalMilliseconds;
 limits='Stage-only slow WMI sample. GPU adapter LUIDs may include integrated and discrete devices; NVIDIA-only zero does not mean all GPU memory is zero. Shared working sets/cache overlap; private commit is not resident RAM. No environment, command line or credentials are collected.'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output),($tpValue|ConvertTo-Json -Depth 6))
[ordered]@{status='OBSERVED';processes=$tpRows.Count;gpu_adapters=$tpGpu.Count;gpu_processes=$tpGpuProcess.Count;elapsed_ms=$tpTime.Elapsed.TotalMilliseconds;errors=$tpErrors}|ConvertTo-Json
