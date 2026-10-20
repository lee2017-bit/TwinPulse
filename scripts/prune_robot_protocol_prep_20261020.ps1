# SPDX-License-Identifier: Apache-2.0
# Only this task's two never-executed intermediate packages. Raw evidence stays.
param([switch]$Apply,[switch]$LayoutIntermediates,[switch]$UnusedTimingBuilds)
$ErrorActionPreference='Stop'
$tpRoot='C:\Users\jaewo\Documents\TwinPulse\outputs\robot-protocol-prep-20261020'
$tpStore='C:\Users\jaewo\AppData\Local\TwinPulse\installed'
$tpRuntime='C:\Users\jaewo\AppData\Local\TwinPulse\runtime'
$tpActive=Get-Content -LiteralPath (Join-Path $tpStore 'active-release.json') -Raw|ConvertFrom-Json
if($tpActive.release_id -ne '20261020T034213Z-ee4c39105987'){throw 'Current final release changed'}
if(Test-Path -LiteralPath (Join-Path $tpRuntime 'launcher.lock')){throw 'App must be normally closed'}
$tpCandidates=@(
 @{tag='02';release='20261020T033427Z-89d5f9195a03'},
 @{tag='03';release='20261020T033958Z-a21a22dca7e3'})
$tpCandidateRoot=$tpRoot;$tpSuffix=''
$tpOnlyBuilds=$false
if($LayoutIntermediates){
 $tpCandidateRoot='C:\Users\jaewo\Documents\TwinPulse\outputs\demo-copy-layout-20261020'
 $tpSuffix='-layout'
 $tpCandidates=@(@{tag='03';release='20261020T021516Z-f573de390fbc'},@{tag='04';release='20261020T022132Z-ece071e0da09'})
}
if($UnusedTimingBuilds){
 $tpCandidateRoot='C:\Users\jaewo\Documents\TwinPulse\outputs\robot-timing-settings-20261020'
 $tpSuffix='-unused-timing';$tpOnlyBuilds=$true
 $tpCandidates=@(@{tag='01';release='20261020T003605Z-5ee83c6a66a8'},@{tag='03';release='20261020T004600Z-38893cc4aedf'},@{tag='05';release='20261020T005339Z-49ef372da9e3'})
 foreach($c in $tpCandidates){if(Test-Path -LiteralPath (Join-Path $tpStore ('releases\'+$c.release))){throw 'Expected never-installed candidate was installed'}}
}
$tpTargets=foreach($c in $tpCandidates){
 Join-Path $tpCandidateRoot ('build-'+$c.tag)
 if(-not $tpOnlyBuilds){Join-Path $tpStore ('releases\'+$c.release)}
}
$tpInventory=foreach($path in $tpTargets){
 $absolute=[IO.Path]::GetFullPath($path)
 if($absolute -ne $path -or $path -notin $tpTargets){throw 'Unresolved cleanup path'}
 $item=Get-Item -LiteralPath $path
 if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse target rejected'}
 $parent=$item.Parent
 while($parent){if($parent.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse ancestor rejected'};$parent=$parent.Parent}
 $members=@(Get-ChildItem -LiteralPath $path -Recurse -Force)
 if(@($members|Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Reparse member rejected'}
 $m=$members|Where-Object {-not $_.PSIsContainer}|Measure-Object Length -Sum
 [pscustomobject]@{path=$absolute;files=$m.Count;logical_bytes=$m.Sum}
}
$tpInventory|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $tpRoot ('cleanup'+$tpSuffix+'-inventory.json')) -Encoding UTF8
if(-not $Apply){$tpInventory|ConvertTo-Json -Depth 5;exit 0}
$tpBefore=(Get-PSDrive C).Free
foreach($c in $tpCandidates){
 $source=Join-Path $tpCandidateRoot ('build-'+$c.tag+'\dist\TwinPulse')
 $archive=Join-Path $tpRoot ('preserved'+$tpSuffix+'-v3-'+$c.tag)
 if(Test-Path -LiteralPath $archive){throw 'Preservation directory already exists'}
 New-Item -ItemType Directory -Path $archive|Out-Null
 Copy-Item -LiteralPath (Join-Path $source 'windows-release-manifest.json') -Destination $archive
 $resourceRoot=Join-Path $source '_internal\resources'
 Copy-Item -LiteralPath $resourceRoot -Destination $archive -Recurse
 $original=@(Get-ChildItem -LiteralPath $resourceRoot -File -Recurse)
 foreach($file in $original){
  $relative=$file.FullName.Substring($resourceRoot.Length).TrimStart('\')
  $copy=Join-Path $archive ('resources\'+$relative)
  if((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash){throw 'Source preservation SHA mismatch'}
 }
}
# Exact inventory, active04/rollback561/reproduction01 and all top-level logs excluded.
if(Test-Path -LiteralPath (Join-Path $tpRuntime 'launcher.lock')){throw 'App started during preservation; no deletion'}
$tpCheck=Get-Content -LiteralPath (Join-Path $tpStore 'active-release.json') -Raw|ConvertFrom-Json
if($tpCheck.release_id -ne '20261020T034213Z-ee4c39105987'){throw 'Active release changed during preservation'}
foreach($row in $tpInventory){Remove-Item -LiteralPath $row.path -Recurse -Force}
$tpReceipt=[pscustomobject]@{removed=$tpInventory;free_before=$tpBefore;free_after=(Get-PSDrive C).Free;
 preservation='Exact resource/source copies and manifests retained; unused EXE bytes are not promised recoverable; no raw/user data removed'}
$tpReceipt|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $tpRoot ('cleanup'+$tpSuffix+'-receipt.json')) -Encoding UTF8
$tpReceipt|Select-Object free_before,free_after,preservation|ConvertTo-Json
