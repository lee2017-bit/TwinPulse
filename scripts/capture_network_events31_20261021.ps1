# SPDX-License-Identifier: Apache-2.0
# Read-only event metadata; deliberately excludes SSID, IP, MAC and XML payload.
$ErrorActionPreference='Stop'
$tpRoot=Split-Path $PSScriptRoot -Parent
$tpOut=Join-Path $tpRoot 'outputs/robot-continuous-repair-20261021/network-events31.json'
if(Test-Path -LiteralPath $tpOut){throw 'New evidence required'}
$tpAt=[DateTimeOffset]::Parse('2026-10-21T21:50:01.631+09:00')
$tpStart=$tpAt.AddSeconds(-30).LocalDateTime
$tpEnd=$tpAt.AddSeconds(30).LocalDateTime
$tpRows=@();$tpQueries=@()
foreach($tpLog in @('Microsoft-Windows-NetworkProfile/Operational','Microsoft-Windows-WLAN-AutoConfig/Operational','System')){
 try{
  $tpEvents=@(Get-WinEvent -FilterHashtable @{LogName=$tpLog;StartTime=$tpStart;EndTime=$tpEnd} -ErrorAction Stop)
  if($tpLog -eq 'System'){$tpEvents=@($tpEvents|Where-Object {$_.ProviderName -match 'Tcpip|Netwtw|NDIS|Network|DHCP|WLAN|e1d|Realtek|Service Control Manager'})}
  $tpRows+=@($tpEvents|Select-Object @{Name='at_utc';Expression={$_.TimeCreated.ToUniversalTime().ToString('o')}},Id,RecordId,ProviderName,LogName,LevelDisplayName)
  $tpQueries+=@{log=$tpLog;status='OBSERVED';matches=$tpEvents.Count}
 }catch{$tpQueries+=@{log=$tpLog;status='UNAVAILABLE_OR_NO_MATCH';error_type=$_.Exception.GetType().Name}}
}
$tpValue=[ordered]@{schema='network-event-metadata-1.0';failure_utc=$tpAt.UtcDateTime.ToString('o');window_seconds=30;queries=$tpQueries;events=$tpRows;
 limits='Native ERR_NETWORK_CHANGED identifies Chromium network invalidation, not a proved Wi-Fi/router/driver cause. Missing Windows events do not prove no network change. No settings modified; sensitive event payloads not collected.'}
[IO.File]::WriteAllText($tpOut,($tpValue|ConvertTo-Json -Depth 5))
$tpValue|ConvertTo-Json -Depth 5
