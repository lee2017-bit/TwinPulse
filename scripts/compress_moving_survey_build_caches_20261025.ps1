# SPDX-License-Identifier: Apache-2.0
# Reversible NTFS compression of exact old generated payloads; deletes no data.
$ErrorActionPreference='Stop'
$tpCanonical='C:\Users\jaewo\Documents\TwinPulse'
$tpParent=Join-Path $tpCanonical 'outputs\environment-task-loop-20261025-01'
$tpEvidence=Join-Path $tpCanonical 'outputs\robot-moving-survey-20261025-01\compression02.json'
if(Test-Path -LiteralPath $tpEvidence){throw 'Evidence already exists'}
$tpBefore=(Get-PSDrive C).Free
$tpRows=@()
foreach($tpBuildName in @('build01','build02','build04','build05','build06','build07','build08','build09','build10','build12','build13','build14','build15','build16','build17','build18')){
 foreach($tpPart in @('dist\TwinPulse\_internal')){
  $tpTarget=[IO.Path]::GetFullPath((Join-Path (Join-Path $tpParent $tpBuildName) $tpPart))
  if(-not $tpTarget.StartsWith($tpParent+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Out of scope'}
  if(-not(Test-Path -LiteralPath $tpTarget)){continue}
  $tpObjects=@(Get-Item -LiteralPath $tpTarget)+@(Get-ChildItem -LiteralPath $tpTarget -Recurse -Force)
  if(@($tpObjects|Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Reparse point rejected'}
  $tpFiles=@($tpObjects|Where-Object {-not $_.PSIsContainer})
  $tpHashes=@{};foreach($tpFile in $tpFiles){$tpHashes[$tpFile.FullName]=(Get-FileHash -LiteralPath $tpFile.FullName -Algorithm SHA256).Hash}
  $tpLog=(& compact.exe /c ('/s:'+$tpTarget) /i /q ($tpTarget+'\*') 2>&1|Out-String)
  $tpCode=$LASTEXITCODE
  $tpExact=$true;foreach($tpFile in $tpFiles){if((Get-FileHash -LiteralPath $tpFile.FullName -Algorithm SHA256).Hash -ne $tpHashes[$tpFile.FullName]){$tpExact=$false}}
  $tpRows+= [pscustomobject]@{path=$tpTarget;files=$tpFiles.Count;logical_bytes=($tpFiles|Measure-Object Length -Sum).Sum;exit_code=$tpCode;all_bytes_unchanged=$tpExact;log=$tpLog}
  if(-not $tpExact){throw 'Byte mismatch; compression is not accepted'}
 }
}
$tpAfter=(Get-PSDrive C).Free
$tpResult=[ordered]@{scope='REVERSIBLE_NTFS_COMPRESSION_OLD_GENERATED_PACKAGE_INTERNALS_ONLY';files_deleted=0;source_or_raw_modified=0;free_before_bytes=$tpBefore;free_after_bytes=$tpAfter;free_change_bytes=$tpAfter-$tpBefore;rows=$tpRows}
[IO.File]::WriteAllText($tpEvidence,($tpResult|ConvertTo-Json -Depth 6))
[pscustomobject]@{targets=$tpRows.Count;all_bytes_unchanged=(@($tpRows|Where-Object {-not $_.all_bytes_unchanged}).Count -eq 0);free_before_gib=[math]::Round($tpBefore/1GB,2);free_after_gib=[math]::Round($tpAfter/1GB,2);deleted=0}|ConvertTo-Json
