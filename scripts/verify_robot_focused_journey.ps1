# SPDX-License-Identifier: Apache-2.0
# Main-owned sequential installed BrowserWindow acceptance, not product APIs.
param([Parameter(Mandatory=$true)][string]$Output,[Parameter(Mandatory=$true)][string]$Attempt,
 [Parameter(Mandatory=$true)][string]$PhysicalPrior,[string]$PhysicalReceipt='')
$ErrorActionPreference='Stop'
if($Attempt -notmatch '^[0-9]{2}$'){throw 'Two-digit attempt required'}
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpPrior=Get-Content -LiteralPath $PhysicalPrior -Raw | ConvertFrom-Json
if(-not $tpPrior.operation_id -or -not $tpPrior.project_id -or -not $tpPrior.manifest.stream){throw 'Immutable original powered-run export required before any App start'}
if(-not $PhysicalReceipt){$PhysicalReceipt=Join-Path (Split-Path $PhysicalPrior -Parent) 'receipt.json'}
if(-not (Test-Path -LiteralPath $PhysicalReceipt)){throw 'Original powered receipt required before any App start'}
$tpInstalled=Join-Path $env:LOCALAPPDATA 'TwinPulse/installed/active-release.json'
$tpPinned=Get-Content -LiteralPath $tpInstalled -Raw | ConvertFrom-Json
$tpOut=[IO.Path]::GetFullPath($Output)
$tpFresh=Join-Path $tpOut ('ui-'+$Attempt)
$tpCold=Join-Path $tpOut ('ui-cold-'+$Attempt)
$tpLineage=Join-Path $tpOut ('lineage-'+$Attempt)
$tpHistory=Join-Path $tpOut ('lineage-cold-'+$Attempt)
foreach($tpPath in @($tpFresh,$tpCold,$tpLineage,$tpHistory)){if(Test-Path -LiteralPath $tpPath){throw 'New evidence paths required'}}
function Start-FocusWindow([string]$Evidence){
 $tpCurrent=Get-Content -LiteralPath $tpInstalled -Raw | ConvertFrom-Json
 if($tpCurrent.release_id -ne $tpPinned.release_id -or $tpCurrent.source_manifest_sha256 -ne $tpPinned.source_manifest_sha256){throw 'Installed release changed between journeys; do not combine evidence'}
 $tpUntil=[DateTime]::UtcNow.AddSeconds(30)
 while((Test-Path (Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime/launcher.lock')) -and [DateTime]::UtcNow -lt $tpUntil){Start-Sleep -Milliseconds 500}
 $tpStart=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_installed_electron_ui_test.ps1')
 if($LASTEXITCODE -ne 0){throw 'Installed Test Start failed; no process terminated'}
 [IO.File]::WriteAllText($Evidence,($tpStart -join [Environment]::NewLine))
 $script:tpEndpoint=($tpStart -join [Environment]::NewLine | ConvertFrom-Json).cdp_endpoint
 $script:tpLaunch=($tpStart -join [Environment]::NewLine | ConvertFrom-Json)
 if($script:tpEndpoint -notmatch '^http://127\.0\.0\.1:1922[2-9]$|^http://127\.0\.0\.1:1923[01]$'){throw 'Expected the verified current launch loopback endpoint'}
 Write-Output ($tpStart -join [Environment]::NewLine)
}
function Finish-FocusWindow([string]$Evidence){
 $tpCleanup=Join-Path $env:LOCALAPPDATA ('TwinPulse/runtime/launches/'+$script:tpLaunch.launch_id+'/cleanup-receipt.json')
 $tpUntil=[DateTime]::UtcNow.AddSeconds(60);$tpReceipt=$null;$tpListeners=@();$tpPass=$false
 do{
  if(Test-Path -LiteralPath $tpCleanup){$tpReceipt=Get-Content -LiteralPath $tpCleanup -Raw | ConvertFrom-Json}
  $tpLocked=Test-Path (Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime/launcher.lock')
  $tpPorts=@(8765,([int]([uri]$script:tpEndpoint).Port))
  $tpListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {$_.LocalPort -in $tpPorts})
  $tpSampled=[DateTime]::UtcNow
  $tpPass=$tpSampled -le $tpUntil -and $tpReceipt.launch_id -eq $script:tpLaunch.launch_id -and $tpReceipt.owner_pid -eq $script:tpLaunch.owner_pid -and $tpReceipt.owned_processes_stopped -and -not $tpLocked -and $tpListeners.Count -eq 0
  if($tpPass){break}
  Start-Sleep -Milliseconds 500
 }while([DateTime]::UtcNow -lt $tpUntil)
 $tpValue=[ordered]@{status=$(if($tpPass){'PASS'}else{'FAIL'});launch_id=$script:tpLaunch.launch_id;receipt=$tpReceipt;launcher_lock_present=$tpLocked;listener_count=$tpListeners.Count;listeners=@($tpListeners|Select-Object LocalAddress,LocalPort,OwningProcess);sampled_at_utc=$tpSampled.ToString('o');deadline_utc=$tpUntil.ToString('o');classification='Matching launcher receipt/lock/listener conjunction within the original 60-second cleanup window before the next Start; no process termination'}
 [IO.File]::WriteAllText($Evidence,($tpValue|ConvertTo-Json -Depth 6))
 if(-not $tpPass){throw 'Prior launch cleanup not confirmed; no next Start'}
 # Freeze the matching Kit log now, before the next Start can rotate it.
 & (Join-Path $tpRoot '.venv/Scripts/python.exe') -B (Join-Path $PSScriptRoot 'archive_roomplan_runtime_20261023.py') $script:tpLaunch.launch_id --output-root $tpOut --copy-set ('final'+$Attempt)
 if($LASTEXITCODE -ne 0){throw 'Prior launch original logs not frozen; no next Start'}
}
Start-FocusWindow (Join-Path $tpOut ('start-fresh-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_fleet_ui.mjs') --cdp $script:tpEndpoint --output $tpFresh --phase fresh --record-renderer --viewport-receipts
if($LASTEXITCODE -ne 0){throw 'Fresh whole flow failed; preserve and diagnose before continuing'}
Finish-FocusWindow (Join-Path $tpOut ('cleanup-fresh-'+$Attempt+'.json'))
$tpFreshResult=Get-Content -LiteralPath (Join-Path $tpFresh 'result.json') -Raw | ConvertFrom-Json
Start-FocusWindow (Join-Path $tpOut ('start-cold-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_fleet_ui.mjs') --cdp $script:tpEndpoint --output $tpCold --phase reopen --project $tpFreshResult.project --field-config (Join-Path $tpFresh 'saved-field-config.json') --registration-prior (Join-Path $tpFresh 'result.json')
if($LASTEXITCODE -ne 0){throw 'Cold whole flow failed; preserve and diagnose'}
Finish-FocusWindow (Join-Path $tpOut ('cleanup-cold-'+$Attempt+'.json'))
$tpLabel='Focus Lineage '+$Attempt
Start-FocusWindow (Join-Path $tpOut ('start-lineage-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_lineage_ui.mjs') --cdp $script:tpEndpoint --output $tpLineage --phase run --project $tpFreshResult.project --label $tpLabel --physical-history $tpPrior.operation_id --physical-project $tpPrior.project_id --physical-prior $PhysicalPrior --physical-receipt $PhysicalReceipt
if($LASTEXITCODE -ne 0){throw 'Original 90-degree lineage whole flow failed; no shorter substitute'}
Finish-FocusWindow (Join-Path $tpOut ('cleanup-lineage-'+$Attempt+'.json'))
$tpLineageResult=Get-Content -LiteralPath (Join-Path $tpLineage 'result.json') -Raw | ConvertFrom-Json
Start-FocusWindow (Join-Path $tpOut ('start-history-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_lineage_ui.mjs') --cdp $script:tpEndpoint --output $tpHistory --phase cold --focused-acceptance --project $tpFreshResult.project --label $tpLabel --operation $tpLineageResult.operation_id --prior (Join-Path $tpLineage 'closed-operation.json') --physical-history $tpPrior.operation_id --physical-project $tpPrior.project_id --physical-prior $PhysicalPrior --physical-receipt $PhysicalReceipt --motion-review-prior (Join-Path $tpLineage 'physical-motion-review.json')
if($LASTEXITCODE -ne 0){throw 'Cold immutable history failed'}
Finish-FocusWindow (Join-Path $tpOut ('cleanup-history-'+$Attempt+'.json'))
Write-Output ('Four UI journeys completed on pinned release; not final readiness or physical qualification. Run verify_robot_focus_gate with all required evidence. Project '+$tpFreshResult.project)
