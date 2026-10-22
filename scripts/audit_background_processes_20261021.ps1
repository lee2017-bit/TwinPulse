# SPDX-License-Identifier: Apache-2.0
# Read-only process attribution. Command lines are used only for fixed role matching,
# never printed or saved. No process is stopped and no plugin setting is changed.
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$tpOutput=[IO.Path]::GetFullPath($Output)
if(Test-Path -LiteralPath $tpOutput){throw 'Preserve original audit'}
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpOut=Join-Path $tpRoot 'outputs/robot-continuous-repair-20261021'
$tpAt=[DateTimeOffset]::Now
$tpAll=@(Get-CimInstance Win32_Process)
$tpMemory=@{}
foreach($tpP in Get-Process){$tpMemory[[int]$tpP.Id]=$tpP}
$tpById=@{}
foreach($tpP in $tpAll){$tpById[[int]$tpP.ProcessId]=$tpP}
$tpRows=@(foreach($tpP in $tpAll){
 $tpCmd=[string]$tpP.CommandLine
 $tpExe=[string]$tpP.ExecutablePath
 $tpMem=$tpMemory[[int]$tpP.ProcessId]
 $tpParent=$tpById[[int]$tpP.ParentProcessId]
 $tpCurrentInspection=$tpP.ProcessId -eq $PID
 $tpRole=if($tpCurrentInspection){'CURRENT_AUDIT_NOT_A_LEAK'}
 elseif($tpP.Name -match '^(TwinPulse.*|kit)\.exe$' -or $tpExe -match '\\TwinPulse\\'){'TWINPULSE_APP_OR_ENGINE'}
 elseif($tpCmd -match '(?i)verify_robot|record_rendered_page|record_windows_memory|robot_powered_ui|twinpulse_engine_host|twinpulse_scan_worker|build_continuous_candidate' -or ($tpCmd -match '(?i)TwinPulse' -and $tpP.Name -match '^(python.*|ffmpeg|node|pwsh|powershell|cmd)\.exe$')){'TWINPULSE_TASK_CANDIDATE'}
 elseif($tpCmd -match '(?i)\brea\b|reverse-engineer-anything|rea-mcp|mcp-rea'){'REA_TOOL_TRANSPORT'}
 elseif($tpP.Name -match '^codex-computer-use' -or $tpExe -match '\\cua_node\\' -or $tpCmd -match '\\cua_node\\'){'COMPUTER_USE_OR_NODE_TOOL_RUNTIME'}
 elseif($tpExe -match '(?i)\\WindowsApps\\OpenAI\.Codex_' -or $tpP.Name -eq 'codex-code-mode-host.exe'){'CODEX_APP_OR_ENGINE'}
 elseif($tpCmd -match '(?i)\bmcp\b' -and $tpParent.Name -eq 'codex.exe'){'OTHER_CONFIGURED_MCP_TRANSPORT'}
 elseif($tpP.Name -match '^(python.*|ffmpeg|electron|chrome|msedge)\.exe$'){'OTHER_RELEVANT_EXECUTABLE_UNATTRIBUTED'}
 else{'OTHER'}
 $tpCreated=[DateTimeOffset]$tpP.CreationDate
 [pscustomobject]@{pid=[int]$tpP.ProcessId;parent_pid=[int]$tpP.ParentProcessId;name=$tpP.Name;
   created_utc=$tpCreated.ToUniversalTime().ToString('o');created_unix_ms=$tpCreated.ToUnixTimeMilliseconds();
   role=$tpRole;parent_name=$tpParent.Name;
   current_parent_creation_order_valid=($null -ne $tpParent -and $tpParent.CreationDate -le $tpP.CreationDate);
   working_set_bytes=$tpMem.WorkingSet64;private_commit_bytes=$tpMem.PrivateMemorySize64;
   cumulative_cpu_s=$tpMem.CPU;handles=$tpMem.Handles}
})
$tpHistorical=@{}
foreach($tpNormal in @('normal31','normal31-restart')){
 $tpBefore=Get-Content -LiteralPath (Join-Path $tpOut ($tpNormal+'/before-shutdown.json')) -Raw|ConvertFrom-Json
 foreach($tpP in $tpBefore.processes){
  $tpTime=[DateTimeOffset]::Parse($tpP.created).ToUnixTimeMilliseconds()
  $tpHistorical[[string]$tpP.pid+':'+[string]$tpTime]=[pscustomobject]@{pid=[int]$tpP.pid;name=$tpP.name;created_unix_ms=$tpTime;basis=$tpNormal}
 }
}
$tpMemoryPath=Join-Path $tpOut 'memory-final31/samples.jsonl'
foreach($tpLine in [IO.File]::ReadLines($tpMemoryPath)){
 $tpSample=$tpLine|ConvertFrom-Json
 foreach($tpP in $tpSample.processes){
  if($tpP.role -match '^(owner|engine|backend)' -and $null -ne $tpP.created_unix_ms){
   $tpTime=[long][math]::Round($tpP.created_unix_ms)
   $tpHistorical[[string]$tpP.pid+':'+[string]$tpTime]=[pscustomobject]@{pid=[int]$tpP.pid;name=$tpP.name;created_unix_ms=$tpTime;basis='LAUNCH_BOUND_MEMORY31_OWNER_ROLE'}
  }
 }
}
$tpStill=@();$tpReused=@()
foreach($tpOld in $tpHistorical.Values){
 $tpCurrent=@($tpRows|Where-Object pid -eq $tpOld.pid)
 foreach($tpNow in $tpCurrent){
  if([math]::Abs($tpNow.created_unix_ms-$tpOld.created_unix_ms) -le 1){$tpStill+=[pscustomobject]@{old=$tpOld;current=$tpNow}}
  else{$tpReused+=[pscustomobject]@{old=$tpOld;current=$tpNow;meaning='PID_REUSED_NOT_OLD_TWINPULSE_PROCESS'}}
 }
}
$tpGroups=@($tpRows|Where-Object role -ne 'OTHER'|Group-Object role|ForEach-Object {
 [pscustomobject]@{role=$_.Name;process_count=$_.Count;observed_working_set_sum_bytes=($_.Group|Measure-Object working_set_bytes -Sum).Sum;
 observed_private_commit_sum_bytes=($_.Group|Measure-Object private_commit_bytes -Sum).Sum}
})
$tpOs=Get-CimInstance Win32_OperatingSystem
$tpValue=[ordered]@{
 schema='background-process-readonly-audit-1.0';sampled_at=$tpAt.ToString('o');
 status='OBSERVATION_NOT_ROOT_CAUSE_OR_CLEANUP_CERTIFICATION';
 historical_owned_identity_count=$tpHistorical.Count;historical_owned_still_alive=$tpStill;reused_pids_not_old_processes=$tpReused;
 groups=$tpGroups;relevant_processes=@($tpRows|Where-Object role -ne 'OTHER');
 dwm=@($tpRows|Where-Object name -eq 'dwm.exe');
 physical_available_bytes=([long]$tpOs.FreePhysicalMemory*1024);
 twinpulse_lock_present=(Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'TwinPulse/runtime/launcher.lock'));
 twinpulse_listener_ports=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object {$_.LocalPort -eq 8765 -or ($_.LocalPort -ge 19222 -and $_.LocalPort -le 19231)}|ForEach-Object {$_.LocalPort});
 source_memory_reference=[ordered]@{path='memory-final31/samples.jsonl';sha256=(Get-FileHash -LiteralPath $tpMemoryPath -Algorithm SHA256).Hash.ToLowerInvariant()};
 limits=@('Historical PID plus creation identity, not PID alone. Unobserved old or inaccessible process ancestry remains outside this check.',
 'Tool runtime groups are current Codex children. Residency is observed, but whether each client context can safely be released is not established.',
 'Working-set sums include shared pages and are not disjoint physical-RAM accounting. Private commit is not physical RAM or actual pagefile bytes.',
 'No claim that a remaining process caused DWM growth or that a driver is the confirmed cause.',
 'Raw command lines, environment variables, network addresses, tokens and credentials are not stored.');
 actions=[ordered]@{process_stop=0;app_start=0;driver_install=0;settings_change=0;robot=0;network_upload=0}
}
[IO.File]::WriteAllText($tpOutput,($tpValue|ConvertTo-Json -Depth 8))
[pscustomobject]@{sampled_at=$tpValue.sampled_at;historical_owned_identity_count=$tpHistorical.Count;historical_owned_still_alive_count=$tpStill.Count;
 twinpulse_app_count=@($tpRows|Where-Object role -eq 'TWINPULSE_APP_OR_ENGINE').Count;twinpulse_task_candidates=@($tpRows|Where-Object role -eq 'TWINPULSE_TASK_CANDIDATE');
 reused_pid_count=$tpReused.Count;groups=$tpGroups;dwm=$tpValue.dwm;physical_available_bytes=$tpValue.physical_available_bytes;
 lock=$tpValue.twinpulse_lock_present;ports=$tpValue.twinpulse_listener_ports}|ConvertTo-Json -Depth 5
