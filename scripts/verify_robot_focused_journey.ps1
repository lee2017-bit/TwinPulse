# SPDX-License-Identifier: Apache-2.0
# Main-owned sequential installed BrowserWindow acceptance, not product APIs.
param([Parameter(Mandatory=$true)][string]$Output,[Parameter(Mandatory=$true)][string]$Attempt)
$ErrorActionPreference='Stop'
if($Attempt -notmatch '^[0-9]{2}$'){throw 'Two-digit attempt required'}
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpOut=[IO.Path]::GetFullPath($Output)
$tpFresh=Join-Path $tpOut ('ui-'+$Attempt)
$tpCold=Join-Path $tpOut ('ui-cold-'+$Attempt)
$tpLineage=Join-Path $tpOut ('lineage-'+$Attempt)
$tpHistory=Join-Path $tpOut ('lineage-cold-'+$Attempt)
foreach($tpPath in @($tpFresh,$tpCold,$tpLineage,$tpHistory)){if(Test-Path -LiteralPath $tpPath){throw 'New evidence paths required'}}
function Start-FocusWindow([string]$Evidence){
 $tpUntil=[DateTime]::UtcNow.AddSeconds(30)
 while((Test-Path (Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime/launcher.lock')) -and [DateTime]::UtcNow -lt $tpUntil){Start-Sleep -Milliseconds 500}
 $tpStart=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_installed_electron_ui_test.ps1')
 if($LASTEXITCODE -ne 0){throw 'Installed Test Start failed; no process terminated'}
 [IO.File]::WriteAllText($Evidence,($tpStart -join [Environment]::NewLine))
 Write-Output ($tpStart -join [Environment]::NewLine)
}
Start-FocusWindow (Join-Path $tpOut ('start-fresh-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_fleet_ui.mjs') --cdp http://127.0.0.1:19222 --output $tpFresh --phase fresh
if($LASTEXITCODE -ne 0){throw 'Fresh whole flow failed; preserve and diagnose before continuing'}
$tpFreshResult=Get-Content -LiteralPath (Join-Path $tpFresh 'result.json') -Raw | ConvertFrom-Json
Start-FocusWindow (Join-Path $tpOut ('start-cold-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_fleet_ui.mjs') --cdp http://127.0.0.1:19222 --output $tpCold --phase reopen --project $tpFreshResult.project --field-config (Join-Path $tpFresh 'saved-field-config.json')
if($LASTEXITCODE -ne 0){throw 'Cold whole flow failed; preserve and diagnose'}
$tpLabel='Focus Lineage '+$Attempt
Start-FocusWindow (Join-Path $tpOut ('start-lineage-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_lineage_ui.mjs') --cdp http://127.0.0.1:19222 --output $tpLineage --phase run --project $tpFreshResult.project --label $tpLabel
if($LASTEXITCODE -ne 0){throw 'Original 90-degree lineage whole flow failed; no shorter substitute'}
$tpLineageResult=Get-Content -LiteralPath (Join-Path $tpLineage 'result.json') -Raw | ConvertFrom-Json
Start-FocusWindow (Join-Path $tpOut ('start-history-'+$Attempt+'.json'))
& node (Join-Path $PSScriptRoot 'verify_robot_lineage_ui.mjs') --cdp http://127.0.0.1:19222 --output $tpHistory --phase cold --project $tpFreshResult.project --label $tpLabel --operation $tpLineageResult.operation_id --prior (Join-Path $tpLineage 'closed-operation.json')
if($LASTEXITCODE -ne 0){throw 'Cold immutable history failed'}
Write-Output ('Whole journey completed on one installed release; project '+$tpFreshResult.project)
