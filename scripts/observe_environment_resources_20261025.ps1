# SPDX-License-Identifier: Apache-2.0
# Bounded read-only PC observation; no process termination or system changes.
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$tpObserveRoot=[IO.Path]::GetFullPath($Output)
$tpRepo=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
if(-not $tpObserveRoot.StartsWith((Join-Path $tpRepo 'outputs\'),[StringComparison]::OrdinalIgnoreCase)){throw 'OUTPUT_OUTSIDE_REPOSITORY'}
New-Item -ItemType Directory -Path $tpObserveRoot -ErrorAction Stop | Out-Null
$tpDeadline=[DateTime]::UtcNow.AddMinutes(30)
$tpStream=[IO.StreamWriter]::new((Join-Path $tpObserveRoot 'samples.jsonl'),$false,[Text.UTF8Encoding]::new($false))
try{
 while([DateTime]::UtcNow -lt $tpDeadline -and -not (Test-Path -LiteralPath (Join-Path $tpObserveRoot 'stop.request'))){
  $tpMemory=Get-CimInstance Win32_OperatingSystem
  $tpPage=Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage
  $tpProcesses=Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -match '^(TwinPulse|TwinPulseDesktop|python|node|Codex|dwm|ffmpeg)$'} | ForEach-Object {
   $tpStarted=$null
   try {if($null -ne $_.StartTime){$tpStarted=$_.StartTime.ToUniversalTime().ToString('o')}} catch {}
   [ordered]@{pid=$_.Id;name=$_.ProcessName;started=$tpStarted;working_bytes=$_.WorkingSet64;private_bytes=$_.PrivateMemorySize64}
  }
  $tpValue=[ordered]@{at=[DateTime]::UtcNow.ToString('o');free_c=(Get-PSDrive C).Free;physical_free_kib=$tpMemory.FreePhysicalMemory;virtual_free_kib=$tpMemory.FreeVirtualMemory;pagefile=$tpPage;processes=@($tpProcesses)}
  $tpStream.WriteLine(($tpValue | ConvertTo-Json -Depth 6 -Compress));$tpStream.Flush()
  Start-Sleep -Seconds 5
 }
}finally{$tpStream.Dispose()}
