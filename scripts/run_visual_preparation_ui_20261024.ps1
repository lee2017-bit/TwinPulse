# SPDX-License-Identifier: Apache-2.0
# Main-owned actual installed BrowserWindow journeys. No API mutation, robot or model calls.
param([Parameter(Mandatory=$true)][string]$OutputRoot,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9]{2}$')][string]$Tag,
 [string]$ColdPrior='', [string]$OriginalColdProject='')
$ErrorActionPreference='Stop'
$tpRepo=Split-Path $PSScriptRoot -Parent
Set-Location $tpRepo
$tpOutput=[IO.Path]::GetFullPath($OutputRoot)
$tpActivePath=Join-Path $env:LOCALAPPDATA 'TwinPulse/installed/active-release.json'
$tpPin=Get-Content -LiteralPath $tpActivePath -Raw | ConvertFrom-Json
function Start-VisualWindow([string]$Name){
 $tpActive=Get-Content -LiteralPath $tpActivePath -Raw | ConvertFrom-Json
 if($tpActive.release_id -ne $tpPin.release_id -or $tpActive.source_manifest_sha256 -ne $tpPin.source_manifest_sha256){throw 'Release changed between journeys'}
 if((Get-PSDrive C).Free -lt 5GB){throw 'Insufficient free disk before recorded session; no data deleted'}
 $tpPath=Join-Path $tpOutput ($Name+'.json');if(Test-Path -LiteralPath $tpPath){throw 'New Start evidence required'}
 $tpJson=& powershell.exe -NoProfile -File scripts/start_installed_electron_ui_test.ps1
 if($LASTEXITCODE -ne 0){throw 'Installed Start failed'}
 [IO.File]::WriteAllText($tpPath,($tpJson -join [Environment]::NewLine))
 $script:tpLaunch=($tpJson -join [Environment]::NewLine | ConvertFrom-Json).launch_id
}
function Run-VisualPhase([string]$Driver,[string]$Phase,[string]$Name,[string[]]$Extra=@()){
 $tpDir=Join-Path $tpOutput $Name;if(Test-Path -LiteralPath $tpDir){throw 'New raw UI evidence required'}
 & node (Join-Path $PSScriptRoot $Driver) $Phase $tpDir @Extra > (Join-Path $tpOutput ($Name+'.log')) 2>&1
 if($LASTEXITCODE -ne 0){throw ($Name+' whole journey failed; original App/evidence retained, no continuation counted as PASS')}
 Write-Output ($Name+' completed')
}
function Finish-VisualWindow([string]$Name){
 Run-VisualPhase 'verify_roomplan_ui_20261023.mjs' 'exit' $Name
 & (Join-Path $tpRepo '.venv/Scripts/python.exe') -B scripts/archive_roomplan_runtime_20261023.py $script:tpLaunch --output-root $tpOutput --copy-set $Tag > (Join-Path $tpOutput ($Name+'-archive.log')) 2>&1
 if($LASTEXITCODE -ne 0){throw 'Original runtime/Kit shutdown copy failed; no next Start'}
}
function Read-SimIdentity([string]$Path){
 # Original response captures can contain tens of MB of mesh JSON. Parse them
 # once in Node and return only the same coordinator fields, not the body tree
 # as millions of PowerShell objects. The original record is never rewritten.
 $tpText=& node -e "const v=JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'));process.stdout.write(JSON.stringify({phase:v.phase,status:v.status,hardware_actions:v.hardware_actions,project_id:v.project_id,operation_id:v.operation_id,versions:v.versions}));" $Path
 if($LASTEXITCODE -ne 0){throw 'Original SIM identity unreadable'}
 return ($tpText | ConvertFrom-Json)
}
if($ColdPrior){
 $tpSim=Read-SimIdentity $ColdPrior
 if($tpSim.phase -ne 'sim' -or $tpSim.status -notin @('PASS','PASS_WITH_EXPECTED_STOP_REJECTION') -or $tpSim.versions.engine.release_id -ne $tpPin.release_id -or $tpSim.hardware_actions -ne 0){throw 'Separate cold requires an actual current-release passed original SIM journey'}
}else{
Start-VisualWindow ('start-fresh-'+$Tag)
Run-VisualPhase 'verify_roomplan_ui_20261023.mjs' 'import' ('roomplan-import'+$Tag)
Run-VisualPhase 'verify_roomplan_ui_20261023.mjs' 'edit' ('roomplan-edit'+$Tag)
Run-VisualPhase 'verify_roomplan_ui_20261023.mjs' 'sim' ('roomplan-sim'+$Tag)
$tpSim=Read-SimIdentity (Join-Path $tpOutput ('roomplan-sim'+$Tag+'/result.json'))
$tpSimLabel='RoomPlan SIM roomplan-sim'+$Tag
Run-VisualPhase 'verify_roomplan_ui_20261023.mjs' 'final-log' ('roomplan-final-log'+$Tag) @($tpSimLabel,$tpSim.operation_id)
Run-VisualPhase 'verify_visual_preparation_ui_20261024.mjs' 'extra' ('ui-extra'+$Tag)
Run-VisualPhase 'verify_visual_preparation_ui_20261024.mjs' 'marker' ('ui-marker'+$Tag)
Finish-VisualWindow ('exit-fresh-'+$Tag)
}
Start-VisualWindow ('start-cold-'+$Tag)
Run-VisualPhase 'verify_roomplan_ui_20261023.mjs' 'cold' ('roomplan-cold'+$Tag) @($tpSim.project_id)
Run-VisualPhase 'verify_visual_preparation_ui_20261024.mjs' 'restore' ('ui-restore'+$Tag)
if($OriginalColdProject){
 if($OriginalColdProject -notmatch '^chat_[a-z0-9_]+$'){throw 'Exact original project identity required'}
 Run-VisualPhase 'verify_roomplan_ui_20261023.mjs' 'cold' ('roomplan-original-cold'+$Tag) @($OriginalColdProject)
}
Finish-VisualWindow ('exit-cold-'+$Tag)
Write-Output 'Current-release actual UI journeys completed; run pixel review/evidence gate before a readiness verdict.'
