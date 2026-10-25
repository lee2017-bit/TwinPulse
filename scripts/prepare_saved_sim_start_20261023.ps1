# SPDX-License-Identifier: Apache-2.0
# Start/prepare/close only the existing installed SIM; no whole-test PASS implied.
param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9]{2}$')][string]$Attempt,
 [ValidateSet('after-bed-rejection','after-final-stop')][string]$Profile='after-bed-rejection',
 [string]$Prior='ui-reproduction-07/result.json',
 [string]$Output='')
$ErrorActionPreference='Stop'
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpOut=Join-Path $tpRoot 'outputs/robot-roomplan-ready-20261023'
if($Output){$tpOut=[IO.Path]::GetFullPath($Output)}
if(Test-Path -LiteralPath (Join-Path $tpOut ('start-preparation'+$Attempt+'.json'))){throw 'New preparation evidence required'}
$tpText=(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_installed_electron_ui_test.ps1')) -join [Environment]::NewLine
if($LASTEXITCODE -ne 0){throw 'Installed Start failed'}
[IO.File]::WriteAllText((Join-Path $tpOut ('start-preparation'+$Attempt+'.json')),$tpText)
$tpLaunch=$tpText|ConvertFrom-Json
$tpPrior=[IO.Path]::GetFullPath((Join-Path $tpOut $Prior))
if(-not $tpPrior.StartsWith($tpOut+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Prior must remain in the exact evidence root'}
& node (Join-Path $PSScriptRoot 'prepare_saved_sim_start_20261023.mjs') --cdp $tpLaunch.cdp_endpoint --output (Join-Path $tpOut ('reproduction'+$Attempt+'-start-preparation')) --prior $tpPrior --profile $Profile
if($LASTEXITCODE -ne 0){throw 'Explicit preparation failed; preserve and stop, no whole-test continuation'}
$tpUntil=[DateTime]::UtcNow.AddSeconds(60)
do{
 $tpPath=Join-Path $env:LOCALAPPDATA ('TwinPulse/runtime/launches/'+$tpLaunch.launch_id+'/cleanup-receipt.json')
 $tpReceipt=$null
 if(Test-Path -LiteralPath $tpPath){$tpReceipt=Get-Content -LiteralPath $tpPath -Raw|ConvertFrom-Json}
 $tpLock=Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime/launcher.lock')
 $tpPorts=@(8765,([int]([uri]$tpLaunch.cdp_endpoint).Port))
 $tpListeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|Where-Object {$_.LocalPort -in $tpPorts})
 $tpRoots=@('engine','backend' | Where-Object {$tpRole=$_;$tpExit=$tpReceipt.process_exit_observations.$tpRole;-not $tpExit.evidence_complete -or $tpExit.root_disposition -ne 'EXITED_DURING_GRACE' -or $tpExit.return_code -ne 0})
 $tpSampled=[DateTime]::UtcNow
 $tpPass=$tpSampled -le $tpUntil -and $tpReceipt.launch_id -eq $tpLaunch.launch_id -and $tpReceipt.owner_pid -eq $tpLaunch.owner_pid -and $tpReceipt.owned_processes_stopped -and $tpReceipt.exit_evidence_complete -and $tpRoots.Count -eq 0 -and -not $tpLock -and $tpListeners.Count -eq 0
 if($tpPass){break};Start-Sleep -Milliseconds 500
}while([DateTime]::UtcNow -lt $tpUntil)
$tpValue=[ordered]@{status=$(if($tpPass){'PASS'}else{'FAIL'});launch_id=$tpLaunch.launch_id;receipt=$tpReceipt;launcher_lock_present=$tpLock;listener_count=$tpListeners.Count;sampled_at_utc=$tpSampled.ToString('o');deadline_utc=$tpUntil.ToString('o');classification='Explicit visible SIM preparation and normal cleanup, not original failure or whole acceptance replacement'}
[IO.File]::WriteAllText((Join-Path $tpOut ('cleanup-preparation'+$Attempt+'.json')),($tpValue|ConvertTo-Json -Depth 6))
$tpValue|ConvertTo-Json -Depth 6
if(-not $tpPass){throw 'Preparation cleanup unconfirmed'}
