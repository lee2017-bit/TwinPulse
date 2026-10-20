# SPDX-License-Identifier: Apache-2.0
# Execute only the fixed path guard AST; no cleanup script body or deletion.
$ErrorActionPreference='Stop'
$tpRepo='C:\Users\jaewo\Documents\TwinPulse'
$tpRoots=@((Join-Path $tpRepo 'outputs'),(Join-Path $tpRepo 'artifacts'),'C:\Users\jaewo\AppData\Local\TwinPulse\installed\releases')
$tpErrors=$null;$tpTokens=$null
$tpAst=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'prune_twinpulse_checkpoint_builds.ps1'),[ref]$tpTokens,[ref]$tpErrors)
if($tpErrors.Count){throw 'POWERSHELL_SYNTAX_ERRORS'}
$tpFunction=$tpAst.Find({param($a) $a -is [Management.Automation.Language.FunctionDefinitionAst] -and $a.Name -eq 'Assert-TpPath'},$true)
Set-Item Function:\Assert-TpPath -Value $tpFunction.Body.GetScriptBlock()
$tpRejected=@('C:\Users\jaewo\Documents\Codex','C:\isaacsim','C:\pagefile.sys','C:\Users\jaewo\Documents\TwinPulse','C:\Users\jaewo\Documents\TwinPulse\outputs','C:\Users\jaewo\Documents\TwinPulse-other\outputs\build-01','C:\Users\jaewo\AppData\Local\TwinPulse\runtime','C:\Users\jaewo\Documents\TwinPulse\outputs\..\README.md')
foreach($path in $tpRejected){$rejected=$false;try{Assert-TpPath $path|Out-Null}catch{$rejected=$true};if(-not $rejected){throw ('UNSAFE_PATH_ACCEPTED: '+$path)}}
foreach($path in @('C:\Users\jaewo\Documents\TwinPulse\outputs\robot-protocol-prep-20261020\build-04\dist\TwinPulse','C:\Users\jaewo\AppData\Local\TwinPulse\installed\releases\20261020T034213Z-ee4c39105987')){
 if((Assert-TpPath $path -Members) -ne $path){throw 'EXPECTED_CANONICAL_PATH_NOT_ACCEPTED'}
}
Write-Output '{"status":"PASS","negative_paths":8,"positive_paths":2,"deleted":0,"scope":"path guard only; no production cleanup execution"}'
