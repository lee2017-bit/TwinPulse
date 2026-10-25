# SPDX-License-Identifier: Apache-2.0
# Sequential actual installed UI journeys, hardware stays OFF.
param([Parameter(Mandatory=$true)][string]$Output,[Parameter(Mandatory=$true)][string]$Attempt)
$ErrorActionPreference='Stop'
if($Attempt -notmatch '^[0-9]{2}$'){throw 'Two-digit attempt required'}
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpOut=[IO.Path]::GetFullPath($Output)
$tpInstalled=Join-Path $env:LOCALAPPDATA 'TwinPulse/installed/active-release.json'
$tpPinned=Get-Content $tpInstalled -Raw|ConvertFrom-Json
function Start-RoomWindow([string]$Branch){
 $tpActive=Get-Content $tpInstalled -Raw|ConvertFrom-Json
 if($tpActive.release_id -ne $tpPinned.release_id -or $tpActive.source_manifest_sha256 -ne $tpPinned.source_manifest_sha256){throw 'Release changed'}
 $tpStart=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_installed_electron_ui_test.ps1')
 if($LASTEXITCODE -ne 0){throw 'Start failed; no process terminated'}
 $tpText=$tpStart -join [Environment]::NewLine
 [IO.File]::WriteAllText((Join-Path $tpOut ('start-roomplan-'+$Branch+'-'+$Attempt+'.json')),$tpText)
 $script:tpLaunch=$tpText|ConvertFrom-Json
 if($script:tpLaunch.cdp_endpoint -ne 'http://127.0.0.1:19222'){throw 'Recorder requires exact current endpoint'}
 Write-Output $tpText
}
function Finish-RoomWindow([string]$Branch){
 $tpRuntime=Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime'
 $tpUntil=[DateTime]::UtcNow.AddSeconds(60);$tpReceipt=$null;$tpPass=$false
 do{
  $tpPath=Join-Path $tpRuntime ('launches/'+$script:tpLaunch.launch_id+'/cleanup-receipt.json')
  if(Test-Path $tpPath){$tpReceipt=Get-Content $tpPath -Raw|ConvertFrom-Json}
  $tpLock=Test-Path (Join-Path $tpRuntime 'launcher.lock')
  $tpListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|Where-Object {$_.LocalPort -in @(8765,19222)})
  $tpPass=$tpReceipt.launch_id -eq $script:tpLaunch.launch_id -and $tpReceipt.owner_pid -eq $script:tpLaunch.owner_pid -and $tpReceipt.owned_processes_stopped -and -not $tpLock -and $tpListeners.Count -eq 0
  if($tpPass){break};Start-Sleep -Milliseconds 500
 }while([DateTime]::UtcNow -lt $tpUntil)
 $tpValue=[ordered]@{status=$(if($tpPass){'PASS'}else{'FAIL'});launch_id=$script:tpLaunch.launch_id;receipt=$tpReceipt;launcher_lock_present=$tpLock;listener_count=$tpListeners.Count;sampled_at_utc=[DateTime]::UtcNow.ToString('o')}
 [IO.File]::WriteAllText((Join-Path $tpOut ('cleanup-roomplan-'+$Branch+'-'+$Attempt+'.json')),($tpValue|ConvertTo-Json -Depth 6))
 if(-not $tpPass){throw 'Cleanup not confirmed; no next Start'}
 & (Join-Path $tpRoot '.venv/Scripts/python.exe') -B (Join-Path $PSScriptRoot 'archive_roomplan_runtime_20261023.py') $script:tpLaunch.launch_id --output-root $tpOut --copy-set ('final'+$Attempt)
 if($LASTEXITCODE -ne 0){throw 'Original launch archive failed'}
}
Start-RoomWindow 'fresh'
foreach($tpPhase in @('import','ai-edit','sim')){
 & node (Join-Path $PSScriptRoot 'verify_roomplan_ui_20261023.mjs') $tpPhase (Join-Path $tpOut ('roomplan-'+$tpPhase+'-'+$Attempt))
 if($LASTEXITCODE -ne 0){throw ('RoomPlan '+$tpPhase+' failed; original retained, no continuation acceptance')}
}
$tpSim=Get-Content (Join-Path $tpOut ('roomplan-sim-'+$Attempt+'/result.json')) -Raw|ConvertFrom-Json
$tpName=$tpSim.registered.label
& node (Join-Path $PSScriptRoot 'verify_roomplan_ui_20261023.mjs') final-log (Join-Path $tpOut ('roomplan-final-log-'+$Attempt)) $tpName $tpSim.operation_id
if($LASTEXITCODE -ne 0){throw 'Finalized operation export failed'}
& node (Join-Path $PSScriptRoot 'verify_roomplan_ui_20261023.mjs') exit (Join-Path $tpOut ('roomplan-exit-'+$Attempt))
if($LASTEXITCODE -ne 0){throw 'Exit failed'}
Finish-RoomWindow 'fresh'
Start-RoomWindow 'cold'
& node (Join-Path $PSScriptRoot 'verify_roomplan_ui_20261023.mjs') cold (Join-Path $tpOut ('roomplan-cold-'+$Attempt)) $tpSim.project_id
if($LASTEXITCODE -ne 0){throw 'RoomPlan cold failed; original retained'}
& node (Join-Path $PSScriptRoot 'verify_roomplan_ui_20261023.mjs') exit (Join-Path $tpOut ('roomplan-cold-exit-'+$Attempt))
if($LASTEXITCODE -ne 0){throw 'Cold Exit failed'}
Finish-RoomWindow 'cold'
Write-Output 'RoomPlan actual UI phases completed; final full evidence gate still required.'
