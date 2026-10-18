# SPDX-License-Identifier: Apache-2.0
# Observation only. It never requests shutdown or kills a process.
param([Parameter(Mandatory=$true)][string]$Normal,[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $Output){throw 'New evidence file required'}
$tpStart=Get-Content -LiteralPath $Normal -Raw | ConvertFrom-Json
$tpRuntime=Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime'
$tpLock=Join-Path $tpRuntime 'launcher.lock'
$tpOwner=Get-Content -LiteralPath $tpLock -Raw | ConvertFrom-Json
if($tpOwner.launch_id -ne $tpStart.launch_id -or $tpOwner.owner_pid -ne $tpStart.owner_pid){throw 'Current owner differs from normal-start evidence'}
$tpAll=@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId)
$tpOwned=@([int]$tpOwner.owner_pid)
do{
 $tpBefore=$tpOwned.Count
 $tpOwned=@($tpOwned+@($tpAll | Where-Object {$_.ParentProcessId -in $tpOwned} | ForEach-Object {[int]$_.ProcessId}) | Select-Object -Unique)
}while($tpOwned.Count -gt $tpBefore)
$tpBegan=[DateTime]::UtcNow
Write-Output ('Observing normal shutdown; launch '+$tpOwner.launch_id+'; owned children '+$tpOwned.Count)
do{
 Start-Sleep -Milliseconds 300
 $tpAlive=@($tpOwned | Where-Object {Get-Process -Id $_ -ErrorAction SilentlyContinue})
 $tpClean=$tpAlive.Count -eq 0 -and -not (Test-Path -LiteralPath $tpLock)
}while(-not $tpClean -and [DateTime]::UtcNow -lt $tpBegan.AddSeconds(60))
$tpApp=@(Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue)
$tpDebug=@(Get-NetTCPConnection -State Listen -LocalPort 19222 -ErrorAction SilentlyContinue)
$tpPass=$tpClean -and $tpApp.Count -eq 0 -and $tpDebug.Count -eq 0
$tpResult=[ordered]@{status=$(if($tpPass){'PASS'}else{'FAIL'});release_id=$tpStart.release_id;source_sha256=$tpStart.source_sha256;
 launch_id=$tpOwner.launch_id;shutdown_clean=$tpPass;observed_elapsed_ms=[math]::Round(([DateTime]::UtcNow-$tpBegan).TotalMilliseconds);
 observed_owned_pids=$tpOwned;remaining_owned_pids=$tpAlive;app_listener_count=$tpApp.Count;debug_listener_count=$tpDebug.Count;
 classification='Read-only cleanup observation. Shutdown input method must be recorded separately; this is not native UI acceptance.'}
$tpJson=$tpResult | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output),$tpJson)
$tpJson
if(-not $tpPass){exit 1}
