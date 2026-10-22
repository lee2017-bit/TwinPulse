# SPDX-License-Identifier: Apache-2.0
# Same normal root entry, not native Explorer. Read-only lifecycle observation.
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpRuntime=Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime'
if(Test-Path -LiteralPath (Join-Path $tpRuntime 'launcher.lock')){throw 'Exit App normally first'}
$tpOut=[IO.Path]::GetFullPath($Output)
if(Test-Path -LiteralPath $tpOut){throw 'New evidence directory required'}
New-Item -ItemType Directory -Path $tpOut | Out-Null
$tpStarted=[DateTime]::UtcNow
$tpEntry=Join-Path $tpRoot 'Start-TwinPulse.cmd'
Start-Process -FilePath $tpEntry -WindowStyle Hidden | Out-Null
$tpUntil=$tpStarted.AddSeconds(120);$tpReady=$false
do{
 Start-Sleep -Milliseconds 500
 try{
  $tpOwner=Get-Content -LiteralPath (Join-Path $tpRuntime 'launcher.lock') -Raw | ConvertFrom-Json
  $tpStatus=Get-Content -LiteralPath (Join-Path $tpRuntime ('launches/'+$tpOwner.launch_id+'/supervisor-status.json')) -Raw | ConvertFrom-Json
  $tpReady=$tpStatus.status -eq 'ready'
 }catch{$tpReady=$false}
}while(-not $tpReady -and [DateTime]::UtcNow -lt $tpUntil)
$tpMs=([DateTime]::UtcNow-$tpStarted).TotalMilliseconds
$tpListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop)
$tpDebug=@($tpListeners | Where-Object {$_.LocalPort -ge 19222 -and $_.LocalPort -le 19231})
$tpApp=@($tpListeners | Where-Object {$_.LocalPort -eq 8765})
Start-Process -FilePath $tpEntry -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 2
$tpAgain=Get-Content -LiteralPath (Join-Path $tpRuntime 'launcher.lock') -Raw | ConvertFrom-Json
$tpActive=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'TwinPulse/installed/active-release.json') -Raw | ConvertFrom-Json
$tpPass=$tpReady -and $tpDebug.Count -eq 0 -and $tpApp.Count -eq 1 -and $tpAgain.launch_id -eq $tpOwner.launch_id -and $tpAgain.owner_pid -eq $tpOwner.owner_pid
$tpResult=[ordered]@{status=$(if($tpPass){'PASS_NORMAL_START_REUSE_DEBUG_OFF'}else{'FAIL_NORMAL_START'});
 release_id=$tpActive.release_id;source_sha256=$tpActive.source_manifest_sha256;launch_id=$tpOwner.launch_id;owner_pid=$tpOwner.owner_pid;
 diagnostic_execution_id=$tpStatus.diagnostic_execution_id;entry=$tpEntry;ready_wait_ms=[math]::Round($tpMs);
 debug_listener_count=$tpDebug.Count;app_listener_count=$tpApp.Count;repeated_start_same_owner=($tpAgain.owner_pid -eq $tpOwner.owner_pid);
 invocation='Execution tool identical root Start, not Explorer double click';native_input='SEPARATELY_RECORDED';hardware_actions=0}
$tpJson=$tpResult | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $tpOut 'result.json'),$tpJson)
$tpJson
