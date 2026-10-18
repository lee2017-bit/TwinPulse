# SPDX-License-Identifier: Apache-2.0
# Read-only process/lock/port receipts. Does not send shutdown or terminate a PID.
param([Parameter(Mandatory=$true)][string]$Output,[switch]$Before,[string]$ReceiptName='shutdown.json')
$ErrorActionPreference='Stop'
$tpOut=[IO.Path]::GetFullPath($Output)
$tpNormal=Get-Content -LiteralPath (Join-Path $tpOut 'result.json') -Raw | ConvertFrom-Json
$tpRuntime=Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime'
if($Before){
 $tpAll=@(Get-CimInstance Win32_Process)
 $tpIds=[Collections.Generic.HashSet[int]]::new();[void]$tpIds.Add([int]$tpNormal.owner_pid)
 do{$tpAdded=$false;foreach($tpProcess in $tpAll){if($tpIds.Contains([int]$tpProcess.ParentProcessId) -and $tpIds.Add([int]$tpProcess.ProcessId)){$tpAdded=$true}}}while($tpAdded)
 $tpRows=@($tpAll | Where-Object {$tpIds.Contains([int]$_.ProcessId)} | ForEach-Object {[pscustomobject]@{pid=$_.ProcessId;created=$_.CreationDate.ToUniversalTime().ToString('o');name=$_.Name}})
 if($tpRows.Count -lt 3){throw 'No owned running App tree was captured'}
 $tpValue=[ordered]@{launch_id=$tpNormal.launch_id;sampled_at=[DateTime]::UtcNow.ToString('o');processes=$tpRows}
 [IO.File]::WriteAllText((Join-Path $tpOut 'before-shutdown.json'),($tpValue|ConvertTo-Json -Depth 5));exit 0
}
$tpBefore=Get-Content -LiteralPath (Join-Path $tpOut 'before-shutdown.json') -Raw | ConvertFrom-Json
$tpStarted=[DateTime]::UtcNow;$tpUntil=$tpStarted.AddSeconds(60)
do{
 $tpAll=@(Get-CimInstance Win32_Process);$tpRemaining=@($tpBefore.processes | Where-Object {$tpItem=$_;@($tpAll | Where-Object {$_.ProcessId -eq $tpItem.pid -and $_.CreationDate.ToUniversalTime().ToString('o') -eq $tpItem.created}).Count -gt 0})
 $tpLocked=Test-Path -LiteralPath (Join-Path $tpRuntime 'launcher.lock')
 if($tpRemaining.Count -eq 0 -and -not $tpLocked){break};Start-Sleep -Milliseconds 500
}while([DateTime]::UtcNow -lt $tpUntil)
$tpApp=@(Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue)
$tpDebug=@(Get-NetTCPConnection -State Listen -LocalPort 19222 -ErrorAction SilentlyContinue)
$tpClean=$tpRemaining.Count -eq 0 -and -not $tpLocked -and $tpApp.Count -eq 0 -and $tpDebug.Count -eq 0
$tpValue=[ordered]@{status=$(if($tpClean){'PASS'}else{'FAIL'});release_id=$tpNormal.release_id;source_sha256=$tpNormal.source_sha256;launch_id=$tpNormal.launch_id;
 shutdown_clean=$tpClean;observed_elapsed_ms=([DateTime]::UtcNow-$tpStarted).TotalMilliseconds;observed_owned_pids=@($tpBefore.processes|ForEach-Object {$_.pid});
 remaining_owned_pids=@($tpRemaining|ForEach-Object {$_.pid});launcher_lock_present=$tpLocked;app_listener_count=$tpApp.Count;debug_listener_count=$tpDebug.Count;
 classification='Read-only cleanup evidence; input method is separately recorded. No process was terminated by this observer.'}
if($ReceiptName -notmatch '^shutdown(-recovery)?\.json$'){throw 'Unsupported receipt name'}
[IO.File]::WriteAllText((Join-Path $tpOut $ReceiptName),($tpValue|ConvertTo-Json -Depth 5));$tpValue|ConvertTo-Json -Depth 5
if(-not $tpClean){exit 1}
