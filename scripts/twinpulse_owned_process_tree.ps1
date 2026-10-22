# SPDX-License-Identifier: Apache-2.0
# Read-only ownership inventory: a reused parent PID is not parent identity.
function Get-TwinPulseOwnedProcessRows {
 param([object[]]$Processes,[int]$RootPid)
 $tpById=@{}
 foreach($tpProcess in $Processes){$tpById[[int]$tpProcess.ProcessId]=$tpProcess}
 if(-not $tpById.ContainsKey($RootPid)){throw 'Current owner process is absent'}
 $tpIds=[Collections.Generic.HashSet[int]]::new();[void]$tpIds.Add($RootPid)
 do {
  $tpAdded=$false
  foreach($tpProcess in $Processes){
   $tpParentId=[int]$tpProcess.ParentProcessId
   if($tpIds.Contains($tpParentId) -and $tpById.ContainsKey($tpParentId) -and
      $tpProcess.CreationDate -ge $tpById[$tpParentId].CreationDate -and
      $tpIds.Add([int]$tpProcess.ProcessId)){$tpAdded=$true}
  }
 }while($tpAdded)
 @($Processes | Where-Object {$tpIds.Contains([int]$_.ProcessId)})
}
