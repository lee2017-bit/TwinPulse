# SPDX-License-Identifier: Apache-2.0
# Maintenance abort only. Never a normal UI/cleanup acceptance result.
$ErrorActionPreference='Stop'
$tpRepo=Split-Path $PSScriptRoot -Parent
$tpRuntime=Join-Path $env:LOCALAPPDATA 'TwinPulse\runtime'
$tpLaunch='7153b94b62e54420b5689c2ea1b9f72e'
$tpEvidence=Join-Path $tpRepo 'outputs\environment-task-loop-20261025-01\aborted13'
if(Test-Path -LiteralPath $tpEvidence){throw 'ATTEMPT_ALREADY_EXISTS'}
$tpLock=Get-Content -LiteralPath (Join-Path $tpRuntime 'launcher.lock') -Raw | ConvertFrom-Json
if($tpLock.launch_id -ne $tpLaunch -or $tpLock.owner_pid -ne 12864){throw 'OWNER_CHANGED'}
$tpOwner=Get-Process -Id $tpLock.owner_pid -ErrorAction Stop
$tpOwnerCim=Get-CimInstance Win32_Process -Filter ('ProcessId='+$tpLock.owner_pid)
if($tpOwner.Path -ne $tpLock.process_identity.executable -or
   $tpOwner.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $tpLock.process_identity.creation_filetime){throw 'OWNER_IDENTITY_CHANGED'}
$tpDesktop=Get-Process -Id 31272 -ErrorAction Stop
$tpDesktopCim=Get-CimInstance Win32_Process -Filter 'ProcessId=31272'
$tpExpectedDesktop=Join-Path (Split-Path $tpOwner.Path -Parent) 'desktop\TwinPulseDesktop.exe'
if($tpDesktop.Path -ne $tpExpectedDesktop -or $tpDesktopCim.ParentProcessId -ne $tpOwner.Id){throw 'DESKTOP_NOT_OWNED'}
New-Item -ItemType Directory -Path $tpEvidence | Out-Null
$tpFolder=Join-Path $tpRuntime ('launches\'+$tpLaunch)
$tpNames=@('backend.log','desktop-host.log','engine.log','engine-result.json','engine-status.json',
 'engine-liveness-observations.json','supervisor-status.json','cleanup-receipt.json','owned-exit-observations.json')
$tpFiles=@($tpNames | ForEach-Object {Join-Path $tpFolder $_})
$tpProject=Join-Path $tpRuntime 'projects\chat_mvmcf9wa_18f1e6d1'
$tpFiles+=@(Join-Path $tpProject 'project.scene-changes.json'; Join-Path $tpProject 'project.scene-edit-transaction.json')
$tpEngineText=Get-Content -LiteralPath (Join-Path $tpFolder 'engine.log') -Raw
if($tpEngineText -match 'Logging to file: ([^\r\n]+)'){
 $tpKit=[IO.Path]::GetFullPath($Matches[1].Trim())
 if((Split-Path $tpKit -Parent) -ne 'C:\isaacsim\kit\logs\Kit\Isaac-Sim Python\6.0' -or
    (Split-Path $tpKit -Leaf) -notmatch '^kit_[0-9]{8}_[0-9]{6}\.log$'){throw 'KIT_OUTSIDE_EXACT_SCOPE'}
 $tpFiles+=@($tpKit)
}
$tpRows=@(foreach($tpFile in $tpFiles){
 if(Test-Path -LiteralPath $tpFile -PathType Leaf){
  $tpDest=Join-Path $tpEvidence (Split-Path $tpFile -Leaf)
  Copy-Item -LiteralPath $tpFile -Destination $tpDest -ErrorAction Stop
  [ordered]@{name=(Split-Path $tpFile -Leaf);status='LIVE_PRE_ABORT_SNAPSHOT_NOT_TERMINAL_CLEANUP';bytes=(Get-Item -LiteralPath $tpDest).Length;sha256=(Get-FileHash -LiteralPath $tpDest -Algorithm SHA256).Hash.ToLowerInvariant()}
 }else{[ordered]@{name=(Split-Path $tpFile -Leaf);status='NOT_PRESENT_BEFORE_ABORT'}}
})
$tpRecord=[ordered]@{status='ABORT_REQUIRED_NOT_NORMAL_EXIT';launch_id=$tpLaunch;at=[DateTime]::UtcNow.ToString('o');
 reason='Old installed build: retained UNKNOWN; explicit UI recovery failed; Exit disabled. Freeze before replacing with reviewed recovery fix.';
 launcher=@{pid=$tpOwner.Id;exe=$tpOwner.Path;creation_filetime=$tpOwner.StartTime.ToUniversalTime().ToFileTimeUtc()};
 desktop=@{pid=$tpDesktop.Id;exe=$tpDesktop.Path;parent_pid=$tpDesktopCim.ParentProcessId;creation_filetime=$tpDesktop.StartTime.ToUniversalTime().ToFileTimeUtc()};files=$tpRows;
 physical_actions=0;user_files_deleted=0;normal_ui_exit='FAIL';inner_cleanup='UNKNOWN_UNTIL_ORIGINAL_RECEIPT'}
$tpRecord | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $tpEvidence 'pre-abort.json') -Encoding UTF8
# Acquire handles and recheck exact creation identities before maintenance stop.
if($tpOwner.HasExited -or $tpDesktop.HasExited){throw 'PROCESS_EXITED_BEFORE_ABORT'}
if($tpOwner.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $tpLock.process_identity.creation_filetime){throw 'OWNER_CHANGED_BEFORE_ABORT'}
Stop-Process -InputObject $tpDesktop -Force -ErrorAction Stop
Stop-Process -InputObject $tpOwner -Force -ErrorAction Stop
[pscustomobject]@{status='OWN_TEST_LAUNCH_ABORTED_NOT_ACCEPTANCE';launch_id=$tpLaunch;evidence=$tpEvidence} | ConvertTo-Json
