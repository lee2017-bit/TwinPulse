# SPDX-License-Identifier: Apache-2.0
# Identical normal entry, read-only lifecycle evidence; never automates a terminal UI.
param([string]$OutputName = 'normal')
$ErrorActionPreference='Stop'
if ($OutputName -notmatch '^[a-z0-9-]+$') { throw 'Invalid output name' }
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpRuntime=Join-Path $env:LOCALAPPDATA 'TwinPulse\runtime'
$tpOut=Join-Path $tpRoot ('outputs\robot-app-field-tests-20261018\'+$OutputName)
if (Test-Path -LiteralPath (Join-Path $tpRuntime 'launcher.lock')) { throw 'Close existing App normally first' }
New-Item -ItemType Directory -Path $tpOut -ErrorAction Stop | Out-Null
$tpEntry=Join-Path $tpRoot 'Start-TwinPulse.cmd'
$tpStarted=[DateTime]::UtcNow
Start-Process -FilePath $tpEntry -WindowStyle Hidden | Out-Null
$tpUntil=$tpStarted.AddSeconds(120)
$tpReady=$false
do {
    Start-Sleep -Milliseconds 500
    $tpLock=Join-Path $tpRuntime 'launcher.lock'
    if (-not (Test-Path -LiteralPath $tpLock)) { continue }
    try {
        $tpOwner=Get-Content -LiteralPath $tpLock -Raw | ConvertFrom-Json
        $tpStatusPath=Join-Path $tpRuntime ('launches\'+$tpOwner.launch_id+'\supervisor-status.json')
        $tpStatus=Get-Content -LiteralPath $tpStatusPath -Raw | ConvertFrom-Json
        $tpReady=$tpStatus.status -eq 'ready'
    } catch { $tpReady=$false }
} while (-not $tpReady -and [DateTime]::UtcNow -lt $tpUntil)
if (-not $tpReady) { throw 'Normal Start did not reach ready in 120 seconds' }
$tpReadyMs=([DateTime]::UtcNow-$tpStarted).TotalMilliseconds
$tpDebug=@(Get-NetTCPConnection -State Listen -LocalPort 19222 -ErrorAction SilentlyContinue)
$tpApp=@(Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue)
Start-Process -FilePath $tpEntry -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 2
$tpAgain=Get-Content -LiteralPath $tpLock -Raw | ConvertFrom-Json
$tpActive=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'TwinPulse\installed\active-release.json') -Raw | ConvertFrom-Json
$tpResult=[ordered]@{
    schema='normal-installed-entry-verification-1.0'
    status= $(if($tpDebug.Count -eq 0 -and $tpApp.Count -eq 1 -and $tpAgain.launch_id -eq $tpOwner.launch_id -and $tpAgain.owner_pid -eq $tpOwner.owner_pid){'PASS_NORMAL_START_REUSE_DEBUG_OFF'}else{'FAIL_NORMAL_START'})
    release_id=$tpActive.release_id;source_sha256=$tpActive.source_manifest_sha256
    launch_id=$tpOwner.launch_id;owner_pid=$tpOwner.owner_pid
    diagnostic_execution_id=$tpStatus.diagnostic_execution_id
    entry=$tpEntry;invocation='Execution tool Start-Process -WindowStyle Hidden, not Explorer double-click'
    ready_wait_ms=[math]::Round($tpReadyMs);debug_listener_19222_count=$tpDebug.Count;app_listener_8765_count=$tpApp.Count
    repeated_root_start_same_owner=($tpAgain.launch_id -eq $tpOwner.launch_id -and $tpAgain.owner_pid -eq $tpOwner.owner_pid)
    engine_status=$tpStatus.engine;native_input='SEPARATELY_RECORDED';hardware_actions=0
}
$tpJson=$tpResult | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $tpOut 'result.json'),$tpJson)
$tpJson
