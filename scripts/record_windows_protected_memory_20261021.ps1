# SPDX-License-Identifier: Apache-2.0
# .NET's system process projection can observe DWM counters whose native handle is denied.
param([Parameter(Mandatory=$true)][string]$OutputDir,[Parameter(Mandatory=$true)][int]$Duration)
$ErrorActionPreference='Stop'
$tpRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../outputs/robot-continuous-repair-20261021'))
$tpOut=[IO.Path]::GetFullPath($OutputDir)
if(-not $tpOut.StartsWith($tpRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or $Duration -lt 3 -or $Duration -gt 2700){throw 'Bounded local evidence required'}
$tpWriter=[IO.StreamWriter]::new((Join-Path $tpOut 'protected-processes.jsonl'),$false,[Text.UTF8Encoding]::new($false));$tpWriter.AutoFlush=$true
$tpStart=[Diagnostics.Stopwatch]::StartNew()
try{
 while($tpStart.Elapsed.TotalSeconds -lt $Duration -and -not (Test-Path -LiteralPath (Join-Path $tpOut 'stop.request'))){
  $tpTick=[Diagnostics.Stopwatch]::StartNew()
  $tpRows=@(Get-Process dwm,'Memory Compression' -ErrorAction SilentlyContinue | ForEach-Object {
   [ordered]@{pid=$_.Id;name=$_.ProcessName;working_set_bytes=$_.WorkingSet64;private_committed_bytes=$_.PrivateMemorySize64;handles=$_.HandleCount;
    identity_limit='Protected creation time unavailable; this row is observation, not process ownership proof.'}
  })
  $tpWriter.WriteLine((([ordered]@{at_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();rows=$tpRows;sampler_wall_ms=$tpTick.Elapsed.TotalMilliseconds})|ConvertTo-Json -Depth 4 -Compress))
  Start-Sleep -Milliseconds 1000
 }
}finally{$tpWriter.Dispose()}
