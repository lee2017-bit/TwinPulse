# SPDX-License-Identifier: Apache-2.0
# Separate saved-geometry UI retest, not a fresh generation or exact-pose replay.
param([Parameter(Mandatory=$true)][string]$Attempt,
 [string]$Project='chat_mvh1ol39_b80cd487',
 [string]$SceneRevision='2344370ae58f16d394c6e4af2e4d9763c8e3e03a6abfffc9d407d3496e53c3d8')
$ErrorActionPreference='Stop'
if($Attempt -notmatch '^[0-9]{2}$'){throw 'Two-digit attempt required'}
if($Project -notmatch '^chat_[a-z0-9_]+$' -or $SceneRevision -notmatch '^[a-f0-9]{64}$'){throw 'Exact saved project/revision required'}
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpOut=Join-Path $tpRoot 'outputs/robot-continuous-repair-20261021'
$tpEvidence=Join-Path $tpOut ('ui-reproduction-'+$Attempt)
if(Test-Path -LiteralPath $tpEvidence){throw 'New evidence path required'}
$tpStart=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_installed_electron_ui_test.ps1')
if($LASTEXITCODE -ne 0){throw 'Installed Test Start failed'}
$tpText=$tpStart -join [Environment]::NewLine
[IO.File]::WriteAllText((Join-Path $tpOut ('start-reproduction-'+$Attempt+'.json')),$tpText)
$tpLaunch=$tpText|ConvertFrom-Json
& node (Join-Path $PSScriptRoot 'verify_robot_fleet_ui.mjs') --cdp $tpLaunch.cdp_endpoint --output $tpEvidence --phase reproduction --project $Project --scene-revision $SceneRevision --record-renderer --viewport-receipts
if($LASTEXITCODE -ne 0){throw 'Saved-geometry UI reproduction failed; preserve original and diagnose before more Start'}
$tpUntil=[DateTime]::UtcNow.AddSeconds(60)
$tpReceiptPath=Join-Path $env:LOCALAPPDATA ('TwinPulse/runtime/launches/'+$tpLaunch.launch_id+'/cleanup-receipt.json')
do{
 $tpReceipt=$null
 if(Test-Path -LiteralPath $tpReceiptPath){$tpReceipt=Get-Content -LiteralPath $tpReceiptPath -Raw|ConvertFrom-Json}
 $tpLocked=Test-Path (Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime/launcher.lock')
 $tpPorts=@(8765,([int]([uri]$tpLaunch.cdp_endpoint).Port))
 $tpListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|Where-Object {$_.LocalPort -in $tpPorts})
 $tpSampled=[DateTime]::UtcNow
 $tpPass=$tpSampled -le $tpUntil -and $tpReceipt.launch_id -eq $tpLaunch.launch_id -and $tpReceipt.owner_pid -eq $tpLaunch.owner_pid -and $tpReceipt.owned_processes_stopped -and -not $tpLocked -and $tpListeners.Count -eq 0
 if($tpPass){break};Start-Sleep -Milliseconds 500
}while([DateTime]::UtcNow -lt $tpUntil)
$tpValue=[ordered]@{status=$(if($tpPass){'PASS'}else{'FAIL'});launch_id=$tpLaunch.launch_id;receipt=$tpReceipt;launcher_lock_present=$tpLocked;listeners=@($tpListeners|Select-Object LocalAddress,LocalPort,OwningProcess);sampled_at_utc=$tpSampled.ToString('o');deadline_utc=$tpUntil.ToString('o');classification='Separate saved original geometry, not fresh or exact initial pose acceptance; no process terminated'}
[IO.File]::WriteAllText((Join-Path $tpOut ('cleanup-reproduction-'+$Attempt+'.json')),($tpValue|ConvertTo-Json -Depth 6))
if(-not $tpPass){throw 'Saved reproduction cleanup unconfirmed'}
$tpValue|ConvertTo-Json -Depth 6
