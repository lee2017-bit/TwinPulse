# SPDX-License-Identifier: Apache-2.0
# Pure inventory regression: no process is opened, closed or terminated.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'twinpulse_owned_process_tree.ps1')
$tpAt=[datetime]'2026-10-20T08:23:20Z'
$tpRows=@(
 [pscustomobject]@{ProcessId=9956;ParentProcessId=1;CreationDate=$tpAt},
 [pscustomobject]@{ProcessId=18364;ParentProcessId=9956;CreationDate=$tpAt.AddSeconds(13)},
 [pscustomobject]@{ProcessId=24564;ParentProcessId=18364;CreationDate=$tpAt.AddDays(-5)},
 [pscustomobject]@{ProcessId=6708;ParentProcessId=18364;CreationDate=$tpAt.AddSeconds(14)},
 [pscustomobject]@{ProcessId=123;ParentProcessId=6708;CreationDate=$tpAt.AddSeconds(10)},
 [pscustomobject]@{ProcessId=321;ParentProcessId=123;CreationDate=$tpAt.AddSeconds(20)})
$tpActual=@(Get-TwinPulseOwnedProcessRows -Processes $tpRows -RootPid 9956 | ForEach-Object {$_.ProcessId})
if(($tpActual|Sort-Object) -join ',' -ne '6708,9956,18364'){throw ('Wrong ownership set: '+($tpActual -join ','))}
try{Get-TwinPulseOwnedProcessRows -Processes $tpRows -RootPid 9999;throw 'Missing owner accepted'}catch{if($_.Exception.Message -ne 'Current owner process is absent'){throw}}
[pscustomobject]@{status='PASS';classification='PURE_OBSERVER_PID_REUSE_NEGATIVE_NOT_APP_ACCEPTANCE';owned=$tpActual;foreign_old_child_excluded=$true;older_than_parent_excluded=$true;missing_owner_rejected=$true}|ConvertTo-Json
