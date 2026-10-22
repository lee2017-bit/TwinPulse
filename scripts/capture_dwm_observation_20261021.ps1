# SPDX-License-Identifier: Apache-2.0
# Read-only counters; never terminates a process or changes display/network settings.
param([Parameter(Mandatory=$true)][string]$Output,[Parameter(Mandatory=$true)][string]$Label)
$ErrorActionPreference='Stop'
$tpOutput=[IO.Path]::GetFullPath($Output)
if(Test-Path -LiteralPath $tpOutput){throw 'Original observation must not be overwritten'}
if(-not (Test-Path -LiteralPath (Split-Path $tpOutput -Parent))){throw 'Evidence parent must already exist'}
$tpAt=[DateTimeOffset]::Now
$tpOs=Get-CimInstance Win32_OperatingSystem
$tpAll=@(Get-Process)
$tpWlan=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-WLAN-AutoConfig/Operational';StartTime=$tpAt.LocalDateTime.AddMinutes(-10);Id=8001,8003} -ErrorAction SilentlyContinue | Select-Object TimeCreated,Id)
$tpValue=[ordered]@{
 schema='windows-dwm-readonly-observation-1.0';label=$Label;sampled_at=$tpAt.ToString('o');
 boot_at=$tpOs.LastBootUpTime.ToUniversalTime().ToString('o');
 physical_total_bytes=([long]$tpOs.TotalVisibleMemorySize*1024);physical_available_bytes=([long]$tpOs.FreePhysicalMemory*1024);
 dwm=@($tpAll|Where-Object ProcessName -eq 'dwm'|Select-Object Id,WorkingSet64,PrivateMemorySize64,Handles,SessionId);
 twinpulse_or_kit=@($tpAll|Where-Object {$_.ProcessName -in @('TwinPulseDesktop','TwinPulse','kit')}|Select-Object Id,ProcessName,WorkingSet64,PrivateMemorySize64);
 top_private=@($tpAll|Sort-Object PrivateMemorySize64 -Descending|Select-Object -First 15 Id,ProcessName,WorkingSet64,PrivateMemorySize64,Handles,SessionId);
 video_controllers=@(Get-CimInstance Win32_VideoController|Select-Object Name,DriverVersion,DriverDate,Status);
 cpu=@(Get-CimInstance Win32_Processor|Select-Object Name);
 recent_wlan_connect_disconnect=$tpWlan;
 c_free_bytes=(Get-PSDrive C).Free;
 semantics=@('WorkingSet is resident including shared pages, not disjoint RAM accounting.','PrivateMemorySize is private commit, not actual RAM or pagefile usage.','The label records an operator action boundary, not proof of causal attribution.','Only basename/counters/driver metadata are stored; no command line, IP, SSID, keys or document content.');
 actions=[ordered]@{application_start=0;application_input=0;process_termination=0;driver_install=0;system_setting_change=0;robot=0}
}
[IO.File]::WriteAllText($tpOutput,($tpValue|ConvertTo-Json -Depth 6))
[pscustomobject]@{label=$Label;sampled_at=$tpValue.sampled_at;physical_available_bytes=$tpValue.physical_available_bytes;dwm=$tpValue.dwm;twinpulse_count=$tpValue.twinpulse_or_kit.Count;recent_wlan_count=$tpWlan.Count}|ConvertTo-Json -Depth 4
