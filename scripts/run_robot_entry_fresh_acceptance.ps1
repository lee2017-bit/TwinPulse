# SPDX-License-Identifier: Apache-2.0
# Installed real-UI fresh journey followed by independent restore runs.
param([ValidatePattern('^[0-9]{2}b?$')][string]$Tag='07',[switch]$ViewportReceipts,[switch]$CompactLabels,
 [string]$EvidenceRoot='outputs/robot-test-entry-20261019')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$tpOut=[IO.Path]::GetFullPath($EvidenceRoot)
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_installed_electron_ui_test.ps1
if($LASTEXITCODE -ne 0){throw 'Final fresh Start failed; no retry'}
$tpNode=(Get-Command node).Source
$tpRecorder=Start-Process -FilePath $tpNode -ArgumentList @('scripts/record_powered_ui.mjs',(Join-Path $tpOut "recording-fresh$Tag")) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $tpOut "recorder-fresh$Tag.stdout.log") -RedirectStandardError (Join-Path $tpOut "recorder-fresh$Tag.stderr.log")
$tpUiArgs=@('scripts/verify_robot_fleet_ui.mjs','--cdp','http://127.0.0.1:19222','--output',(Join-Path $tpOut "ui-fresh-$Tag"),'--phase','fresh')
if($ViewportReceipts){$tpUiArgs+='--viewport-receipts'}
if($CompactLabels){$tpUiArgs+='--compact-labels'}
& node @tpUiArgs
if($LASTEXITCODE -ne 0){throw 'Final fresh whole journey failed; original evidence/window retained, no next journey'}
for($tpWait=0;$tpWait -lt 6 -and -not $tpRecorder.HasExited;$tpWait++){$tpRecorder.WaitForExit(10000)|Out-Null}
if(-not $tpRecorder.HasExited){throw 'Final fresh recorder did not finish; no next journey'}
$tpSession=Get-Content (Join-Path $tpOut "recording-fresh$Tag/session.json") -Raw | ConvertFrom-Json
if(@($tpSession.events | Where-Object {$_.name -eq 'VIDEO_ENCODE' -and $_.evidence.code -eq 0}).Count -ne 1){throw 'Final fresh encoding not verified'}
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_robot_entry_restore_acceptance.ps1 -Tag $Tag -EvidenceRoot $tpOut
if($LASTEXITCODE -ne 0){throw 'Independent restore journey failed; original failure retained'}
