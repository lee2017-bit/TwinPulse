# SPDX-License-Identifier: Apache-2.0
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$tpInstalled=Join-Path $env:LOCALAPPDATA 'TwinPulse/installed'
$tpActive=Get-Content -LiteralPath (Join-Path $tpInstalled 'active-release.json') -Raw | ConvertFrom-Json
$tpRelease=Split-Path (Join-Path $tpInstalled $tpActive.exe) -Parent
$tpManifest=Get-Content -LiteralPath (Join-Path $tpRelease 'windows-release-manifest.json') -Raw | ConvertFrom-Json
$tpMismatch=@();$tpCount=0
foreach($tpFile in $tpManifest.files){
 $tpPath=[IO.Path]::GetFullPath((Join-Path $tpRelease $tpFile.path))
 if(-not $tpPath.StartsWith($tpRelease+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Path escapes release'}
 if(-not (Test-Path -LiteralPath $tpPath) -or (Get-FileHash -LiteralPath $tpPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tpFile.sha256){$tpMismatch+=$tpFile.path}
 $tpCount++
}
$tpResult=[ordered]@{status=$(if($tpMismatch.Count -eq 0){'PASS'}else{'FAIL'});release_id=$tpActive.release_id;
 source_manifest_sha256=$tpManifest.source_manifest_sha256;channel=$tpManifest.channel;capabilities=$tpManifest.capabilities;file_count=$tpCount;mismatches=$tpMismatch}
$tpJson=$tpResult | ConvertTo-Json -Depth 5
if(Test-Path -LiteralPath $Output){throw 'New evidence file required'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output),$tpJson)
$tpJson
