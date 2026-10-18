# SPDX-License-Identifier: Apache-2.0
# Sequential public installed-UI journeys only; stop on the first failure.
param([ValidateSet('cold','lineage')][string]$StartAt='cold',[ValidatePattern('^[0-9]{2}b?$')][string]$Tag='07',
 [switch]$IndependentAfterFailedFresh,[string]$FieldConfig='',[string]$FreshEvidence='',
 [string]$EvidenceRoot='outputs/robot-test-entry-20261019')
$ErrorActionPreference='Stop'
$tpRoot=Split-Path $PSScriptRoot -Parent
Set-Location $tpRoot
$tpOut=[IO.Path]::GetFullPath($EvidenceRoot)
$tpNode=(Get-Command node).Source
if(-not $FreshEvidence){$FreshEvidence=Join-Path $tpOut "ui-fresh-$Tag/result.json"}
$tpFresh=Get-Content -LiteralPath $FreshEvidence -Raw | ConvertFrom-Json
if($tpFresh.status -ne 'PASS'){
 if(-not $IndependentAfterFailedFresh){throw 'Original fresh journey must pass before independent restore journeys'}
 Write-Output 'INDEPENDENT_DIAGNOSTIC_RESTORES_AFTER_PRESERVED_FRESH_FAILURE_NOT_FULL_CYCLE_PASS'
}
if(-not $FieldConfig){$FieldConfig=Join-Path $tpOut "ui-fresh-$Tag/saved-field-config.json"}
if(-not(Test-Path -LiteralPath $FieldConfig -PathType Leaf)){throw 'Explicit existing offline configuration evidence required; no synthetic or silent fallback'}
function Invoke-TpRecordedJourney([string]$Name,[string]$Script,[string[]]$UiArgs){
 & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_installed_electron_ui_test.ps1
 if($LASTEXITCODE -ne 0){throw "Start failed for $Name; inspect original launch, no retry"}
 $tpRecord=Start-Process -FilePath $tpNode -ArgumentList @('scripts/record_powered_ui.mjs',(Join-Path $tpOut "recording-$Name")) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $tpOut "recorder-$Name.stdout.log") -RedirectStandardError (Join-Path $tpOut "recorder-$Name.stderr.log")
 & $tpNode $Script @UiArgs
 $tpExit=$LASTEXITCODE
 for($tpWait=0;$tpWait -lt 6 -and -not $tpRecord.HasExited;$tpWait++){$tpRecord.WaitForExit(10000)|Out-Null}
 if($tpExit -ne 0){throw "UI journey failed for $Name. Original failure and opened window preserved; no next journey"}
 if(-not $tpRecord.HasExited){throw "Recording still running for $Name; no next journey"}
 # Windows PowerShell may expose a null ExitCode on an already-reaped
 # Start-Process handle. Do not mislabel that as an encoder failure.
 $tpSession=Get-Content -LiteralPath (Join-Path $tpOut "recording-$Name/session.json") -Raw | ConvertFrom-Json
 $tpEncode=@($tpSession.events | Where-Object {$_.name -eq 'VIDEO_ENCODE'})
 if($tpEncode.Count -ne 1 -or $tpEncode[0].evidence.code -ne 0 -or -not(Test-Path -LiteralPath (Join-Path $tpOut "recording-$Name/app-screen.mp4"))){throw "Recorder did not produce verified video for $Name"}
 Write-Output "COMPLETE_RECORDED_JOURNEY $Name"
}
if($StartAt -eq 'cold'){
 Invoke-TpRecordedJourney "cold$Tag" 'scripts/verify_robot_fleet_ui.mjs' @('--cdp','http://127.0.0.1:19222','--output',(Join-Path $tpOut "ui-cold-$Tag"),'--phase','reopen','--project',$tpFresh.project,'--field-config',$FieldConfig)
}else{
 $tpCold=Get-Content -LiteralPath (Join-Path $tpOut "ui-cold-$Tag/result.json") -Raw | ConvertFrom-Json
 if($tpCold.status -ne 'PASS' -or $tpCold.project -ne $tpFresh.project -or $tpCold.desktop.engine.release_id -ne $tpFresh.desktop.engine.release_id){throw 'Cannot skip incomplete/wrong-release cold journey'}
 Write-Output 'Prior independent cold04 whole UI PASS preserved. Orchestrator null-ExitCode error was not a failed or resumed UI journey.'
}
Invoke-TpRecordedJourney "lineage$Tag" 'scripts/verify_robot_lineage_ui.mjs' @('--cdp','http://127.0.0.1:19222','--output',(Join-Path $tpOut "lineage-$Tag"),'--phase','run','--project',$tpFresh.project,'--label',"Lineage Entry $Tag Alpha")
$tpOperation=Get-Content -LiteralPath (Join-Path $tpOut "lineage-$Tag/closed-operation.json") -Raw | ConvertFrom-Json
Invoke-TpRecordedJourney "lineage-cold$Tag" 'scripts/verify_robot_lineage_ui.mjs' @('--cdp','http://127.0.0.1:19222','--output',(Join-Path $tpOut "lineage-cold-$Tag"),'--phase','cold','--project',$tpFresh.project,'--label',"Lineage Entry $Tag Alpha",'--operation',$tpOperation.operation_id,'--prior',(Join-Path $tpOut "lineage-$Tag/closed-operation.json"),'--physical-history','ed7bed76300e45c59930e0be0c923b96','--physical-project','chat_mvcck71j_6d94b13d','--physical-prior','outputs/robot-recovery-powered-20261018/operation-summary.json')
