# SPDX-License-Identifier: Apache-2.0
# One explicit SIM UI preparation; no physical connection or forced termination.
$ErrorActionPreference='Stop'
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpOut=Join-Path $tpRoot 'outputs/robot-continuous-repair-20261021'
$tpStart=& powershell.exe -NoProfile -File (Join-Path $PSScriptRoot 'start_installed_electron_ui_test.ps1')
if($LASTEXITCODE -ne 0){throw 'Existing installed Test entry failed'}
$tpText=$tpStart -join [Environment]::NewLine
$tpStartPath=Join-Path $tpOut 'start-diagnostic49.json'
if(Test-Path -LiteralPath $tpStartPath){throw 'Do not overwrite a prior launch'}
[IO.File]::WriteAllText($tpStartPath,$tpText)
$tpLaunch=$tpText|ConvertFrom-Json
& node (Join-Path $PSScriptRoot 'prepare_saved_sim_clearance_20261022.mjs') --cdp $tpLaunch.cdp_endpoint --output (Join-Path $tpOut 'clearance-preparation49')
$tpUiCode=$LASTEXITCODE
$tpUntil=[DateTime]::UtcNow.AddSeconds(60)
$tpRuntime=Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime'
$tpReceiptPath=Join-Path $tpRuntime ('launches/'+$tpLaunch.launch_id+'/cleanup-receipt.json')
do{
 $tpReceipt=$null
 if(Test-Path -LiteralPath $tpReceiptPath){$tpReceipt=Get-Content -LiteralPath $tpReceiptPath -Raw|ConvertFrom-Json}
 $tpLocked=Test-Path -LiteralPath (Join-Path $tpRuntime 'launcher.lock')
 $tpPorts=@(8765,([int]([uri]$tpLaunch.cdp_endpoint).Port))
 $tpListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|Where-Object {$_.LocalPort -in $tpPorts})
 $tpSampled=[DateTime]::UtcNow
 $tpPass=$tpSampled -le $tpUntil -and $tpReceipt.launch_id -eq $tpLaunch.launch_id -and $tpReceipt.owner_pid -eq $tpLaunch.owner_pid -and $tpReceipt.owned_processes_stopped -and -not $tpLocked -and $tpListeners.Count -eq 0
 if($tpPass){break};Start-Sleep -Milliseconds 500
}while([DateTime]::UtcNow -lt $tpUntil)
$tpValue=[ordered]@{status=$(if($tpPass){'PASS'}else{'FAIL'});launch_id=$tpLaunch.launch_id;receipt=$tpReceipt;launcher_lock_present=$tpLocked;listeners=@($tpListeners|Select-Object LocalAddress,LocalPort,OwningProcess);sampled_at_utc=$tpSampled.ToString('o');deadline_utc=$tpUntil.ToString('o');classification='Independent cleanup only; preparation49 is not original48 acceptance and no process was terminated'}
$tpCleanup=Join-Path $tpOut 'cleanup-preparation49.json'
if(Test-Path -LiteralPath $tpCleanup){throw 'Do not overwrite prior cleanup'}
[IO.File]::WriteAllText($tpCleanup,($tpValue|ConvertTo-Json -Depth 7))
$tpValue|ConvertTo-Json -Depth 7
if($tpUiCode -ne 0 -or -not $tpPass){throw 'Explicit UI preparation or independent cleanup failed; preserve original before any next Start'}
