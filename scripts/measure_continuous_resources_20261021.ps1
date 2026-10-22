# SPDX-License-Identifier: Apache-2.0
# Read-only evidence. Never stops processes or changes system configuration.
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $Output){throw 'New evidence path required'}
$tpOs=Get-CimInstance Win32_OperatingSystem
$tpDrive=Get-PSDrive C
$tpRows=@(Get-Process dwm,TwinPulse,isaac-sim -ErrorAction SilentlyContinue | ForEach-Object {
 [ordered]@{pid=$_.Id;name=$_.ProcessName;working_set_bytes=$_.WorkingSet64;private_committed_bytes=$_.PrivateMemorySize64}
})
$tpValue=[ordered]@{schema='continuous-resources-20261021-1.0';classification='READ_ONLY_OS_SNAPSHOT_NOT_SOLE_CAUSE_PROOF';at_utc=[DateTime]::UtcNow.ToString('o');
 free_physical_kib=$tpOs.FreePhysicalMemory;total_physical_kib=$tpOs.TotalVisibleMemorySize;free_virtual_kib=$tpOs.FreeVirtualMemory;
 total_virtual_kib=$tpOs.TotalVirtualMemorySize;last_boot=$tpOs.LastBootUpTime.ToString('o');disk_free_bytes=$tpDrive.Free;processes=$tpRows;
 limits='Private committed bytes are not physical RAM use or generated model file size. Combined resource pressure does not establish DWM, disk paging or a memory leak as the sole cause. No process or settings were changed.'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output),($tpValue|ConvertTo-Json -Depth 5))
$tpValue|ConvertTo-Json -Depth 5
