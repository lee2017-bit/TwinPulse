# SPDX-License-Identifier: Apache-2.0
# Reviewed generated binaries only. Never deletes source, raw captures or projects.
param([switch]$Apply,[Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$tpRepo='C:\Users\jaewo\Documents\TwinPulse'
$tpStore='C:\Users\jaewo\AppData\Local\TwinPulse\installed'
$tpRoots=@((Join-Path $tpRepo 'outputs'),(Join-Path $tpRepo 'artifacts'),(Join-Path $tpStore 'releases'))
$tpPins=@('20261020T034213Z-ee4c39105987','20261020T022703Z-d349de20d29b','20261019T091021Z-ab4cc1fdeb77','20261020T031424Z-a31becb620c7')
$tpOut=[IO.Path]::GetFullPath($OutputDirectory)
if(-not $tpOut.StartsWith($tpRoots[0]+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'AUDIT_OUTPUT_OUTSIDE_TWINPULSE'}
if(Test-Path -LiteralPath $tpOut){throw 'NEW_AUDIT_OUTPUT_REQUIRED'}
if((Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path -ne $tpRepo){throw 'CANONICAL_REPOSITORY_REQUIRED'}

function Assert-TpPath {
 param([string]$Path,[switch]$Members)
 $full=[IO.Path]::GetFullPath($Path)
 if($full -ne $Path.TrimEnd('\')){throw 'NON_CANONICAL_TARGET_REFUSED'}
 if(-not ($tpRoots|Where-Object {$full.StartsWith($_+'\',[StringComparison]::OrdinalIgnoreCase)})){throw 'OUTSIDE_EXACT_TWINPULSE_GENERATED_ROOTS'}
 if($full -in $tpRoots -or $full -eq $tpRepo -or $full -eq $tpStore){throw 'ROOT_DELETE_REFUSED'}
 $item=Get-Item -Force -LiteralPath $full
 if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_TARGET_REFUSED'}
 $walk=if($item.PSIsContainer){$item}else{$item.Directory}
 while($walk){if($walk.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_ANCESTOR_REFUSED'};$walk=$walk.Parent}
 if($Members -and $item.PSIsContainer){
  # Enumerate level by level; do not traverse a junction before checking it.
  $todo=[Collections.Generic.Stack[string]]::new();$todo.Push($full)
  while($todo.Count){foreach($child in Get-ChildItem -Force -LiteralPath $todo.Pop()){
   if($child.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_MEMBER_REFUSED'}
   if($child.PSIsContainer){$todo.Push($child.FullName)}
  }}
 }
 return $full
}
function Write-TpJson([string]$Path,$Value){$Value|ConvertTo-Json -Depth 14|Set-Content -LiteralPath $Path -Encoding utf8}
function Hash-Tp([string]$Path){return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}

$tpActive=Get-Content -LiteralPath (Join-Path $tpStore 'active-release.json') -Raw|ConvertFrom-Json
if($tpActive.release_id -ne $tpPins[0]){throw 'ACTIVE_FROZEN_CHECKPOINT_CHANGED'}
if(Test-Path -LiteralPath 'C:\Users\jaewo\AppData\Local\TwinPulse\runtime\launcher.lock'){throw 'APP_MUST_BE_NORMALLY_CLOSED'}
foreach($id in $tpPins){if(-not(Test-Path -LiteralPath (Join-Path $tpRoots[2] ($id+'\windows-release-manifest.json')))){throw 'PINNED_PACKAGE_MISSING'}}
$tpProof=$null
if($Apply){
 $tpProof=Get-Content -LiteralPath (Join-Path $tpRepo 'outputs\github-preservation-20261020\remote-verification.json') -Raw|ConvertFrom-Json
 if($tpProof.status -ne 'REMOTE_SOURCE_AND_ARCHIVE_VERIFIED' -or -not $tpProof.private -or $tpProof.repository -ne 'lee2017-bit/TwinPulse' -or $tpProof.release_id -ne $tpPins[0]){throw 'VERIFIED_CURRENT_PRIVATE_ARCHIVE_REQUIRED'}
 if(-not($tpProof.assets|Where-Object {$_.download_verified -and $_.name.EndsWith('.zip')})){throw 'REMOTE_ARCHIVE_DOWNLOAD_HASH_REQUIRED'}
 $head=(& git -C $tpRepo ls-remote origin refs/heads/main) -split '\s+'
 if($LASTEXITCODE -ne 0 -or $head[0] -ne $tpProof.source_commit){throw 'REMOTE_PRESERVED_SOURCE_CHANGED'}
}
New-Item -ItemType Directory -Path $tpOut|Out-Null
$tpTargets=[Collections.Generic.List[object]]::new();$tpProtected=[Collections.Generic.List[object]]::new();$tpPackages=@{}
$tpProcesses=@(Get-CimInstance Win32_Process|Where-Object {$_.Name -in @('TwinPulse.exe','TwinPulseDesktop.exe','kit.exe','python.exe','pythonw.exe')}|Select-Object ProcessId,ExecutablePath,CommandLine)
function Add-TpTarget([string]$Path,[string]$Kind,[string]$Build){
 if(-not(Test-Path -LiteralPath $Path)){return}
 $full=Assert-TpPath $Path -Members
 if($tpTargets|Where-Object path -eq $full){return}
 if($tpProcesses|Where-Object {($_.ExecutablePath -and $_.ExecutablePath.StartsWith($full+'\',[StringComparison]::OrdinalIgnoreCase)) -or ($_.CommandLine -and $_.CommandLine.IndexOf($full,[StringComparison]::OrdinalIgnoreCase) -ge 0)}){$tpProtected.Add(@{path=$full;reason='RUNNING_REFERENCE'});return}
 $item=Get-Item -LiteralPath $full
 $m=if($item.PSIsContainer){Get-ChildItem -LiteralPath $full -Recurse -File -Force|Measure-Object Length -Sum}else{@{Sum=$item.Length;Count=1}}
 $tpTargets.Add([pscustomobject]@{path=$full;kind=$Kind;build_id=$Build;files=$m.Count;logical_bytes=$m.Sum})
}
function Read-TpPackage([string]$Root){
 $full=Assert-TpPath $Root
 $m=Get-Content -LiteralPath (Join-Path $full 'windows-release-manifest.json') -Raw|ConvertFrom-Json
 if($m.schema -ne 'twinpulse-windows-exe-1.0' -or $m.build_id -notmatch '^20\d{6}T\d{6}Z-[a-f0-9]{12}$'){throw 'NOT_A_TWINPULSE_PACKAGE'}
 if($m.build_id -in $tpPins){$tpProtected.Add(@{path=$full;build_id=$m.build_id;reason='CURRENT_ROLLBACK_OR_REQUIRED_REPRO'});return $m}
 $resource=Join-Path $full '_internal\resources'
 if(-not(Test-Path -LiteralPath (Join-Path $resource 'source-manifest.json'))){throw 'SOURCE_SNAPSHOT_MISSING'}
 if(-not $tpPackages.ContainsKey($m.build_id)){$tpPackages[$m.build_id]=@{root=$full;resources=$resource;manifest=(Join-Path $full 'windows-release-manifest.json')}}
 return $m
}
foreach($release in Get-ChildItem -LiteralPath $tpRoots[2] -Directory){
 $m=Read-TpPackage $release.FullName
 if($m.build_id -ne $release.Name){throw 'RELEASE_DIRECTORY_IDENTITY_MISMATCH'}
 if($m.build_id -notin $tpPins){Add-TpTarget $release.FullName 'OBSOLETE_INSTALLED_PACKAGE' $m.build_id}
}
foreach($scope in $tpRoots[0..1]){
 if(-not(Test-Path -LiteralPath $scope)){continue}
 Write-Output ('Scanning generated package manifests under '+$scope)
 # Prune traversal at reparse directories, including dependency junctions.
 $todo=[Collections.Generic.Stack[string]]::new();$todo.Push($scope)
 while($todo.Count){
  $dir=$todo.Pop();$children=@(Get-ChildItem -LiteralPath $dir -Force)
  foreach($child in $children|Where-Object PSIsContainer){if(-not($child.Attributes -band [IO.FileAttributes]::ReparsePoint)){$todo.Push($child.FullName)}}
  if((Split-Path -Leaf $dir) -ne 'TwinPulse' -or (Split-Path -Leaf (Split-Path -Parent $dir)) -ne 'dist'){continue}
  if(-not($children|Where-Object Name -eq 'windows-release-manifest.json')){continue}
  $build=Split-Path -Parent (Split-Path -Parent $dir)
  if((Split-Path -Leaf $build) -notmatch '^(build[-_]?\d+|build|candidate[-_]\d+)$'){$tpProtected.Add(@{path=$dir;reason='UNCLASSIFIED_BUILD_DIRECTORY'});continue}
  $m=Read-TpPackage $dir
  if($m.build_id -in $tpPins){continue}
  Add-TpTarget $dir 'OBSOLETE_GENERATED_PACKAGE' $m.build_id
  foreach($name in @('work','staging','desktop-build')){Add-TpTarget (Join-Path $build $name) 'REPRODUCIBLE_BUILD_INTERMEDIATE' $m.build_id}
  foreach($zip in Get-ChildItem -LiteralPath $build -File -Filter 'TwinPulse-Windows-*.zip'){
   if($zip.Name.Contains($m.build_id)){Add-TpTarget $zip.FullName 'OBSOLETE_BUILDER_ZIP' $m.build_id}
  }
 }
}
$tpPlan=[ordered]@{schema='exact-twinpulse-checkpoint-retention-1.0';apply=[bool]$Apply;allowed_roots=$tpRoots;pins=$tpPins;active=$tpActive;targets=@($tpTargets);protected=@($tpProtected);remote=$tpProof;never_delete=@('source checkout','runtime','photos','projects','sensor raw','logs','recording frames/videos','other Codex paths','Docker/WSL','Isaac installation','Windows files')}
Write-TpJson (Join-Path $tpOut 'plan.json') $tpPlan
Write-Output ([ordered]@{stage='PLAN';targets=$tpTargets.Count;logical_bytes=($tpTargets|Measure-Object logical_bytes -Sum).Sum;protected=$tpProtected.Count;apply=[bool]$Apply}|ConvertTo-Json -Compress)
if(-not $Apply){return}
$tpLock=[IO.File]::Open((Join-Path (Split-Path -Parent $tpStore) 'maintenance.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
try{
 if($tpLock.Length -eq 0){$tpLock.SetLength(1)};$tpLock.Lock(0,1)
 if(Test-Path -LiteralPath 'C:\Users\jaewo\AppData\Local\TwinPulse\runtime\launcher.lock'){throw 'APP_STARTED_DURING_REVIEW'}
 $objects=Join-Path $tpOut 'source-objects';New-Item -ItemType Directory -Path $objects|Out-Null
 $maps=Join-Path $tpOut 'source-maps';New-Item -ItemType Directory -Path $maps|Out-Null
 foreach($id in $tpPackages.Keys){
  $package=$tpPackages[$id];$resource=Assert-TpPath $package.resources -Members;$map=[Collections.Generic.List[object]]::new()
  foreach($file in Get-ChildItem -LiteralPath $resource -File -Recurse -Force){
   $hash=Hash-Tp $file.FullName;$object=Join-Path $objects $hash
   if(-not(Test-Path -LiteralPath $object)){Copy-Item -LiteralPath $file.FullName -Destination $object}
   if((Hash-Tp $object) -ne $hash){throw 'SOURCE_PRESERVATION_HASH_MISMATCH'}
   $map.Add(@{path=$file.FullName.Substring($resource.Length+1);sha256=$hash;bytes=$file.Length})
  }
  Copy-Item -LiteralPath $package.manifest -Destination (Join-Path $maps ($id+'-windows-manifest.json'))
  Write-TpJson (Join-Path $maps ($id+'-resources.json')) @{build_id=$id;schema='content-addressed-preserved-resources-1.0';files=@($map)}
 }
 $before=(Get-PSDrive C).Free;$results=[Collections.Generic.List[object]]::new();$index=0
 foreach($target in $tpTargets){
  $now=Get-Content -LiteralPath (Join-Path $tpStore 'active-release.json') -Raw|ConvertFrom-Json
  if($now.release_id -ne $tpPins[0]){throw 'ACTIVE_RELEASE_CHANGED_DURING_MAINTENANCE'}
  $full=Assert-TpPath $target.path -Members
  try{Remove-Item -LiteralPath $full -Recurse -Force;if(Test-Path -LiteralPath $full){throw 'TARGET_STILL_PRESENT'};$results.Add(@{path=$full;status='REMOVED';logical_bytes=$target.logical_bytes})}
  catch{$results.Add(@{path=$full;status='FAILED';error_type=$_.Exception.GetType().Name})}
  $index++;if($index%20 -eq 0){Write-TpJson (Join-Path $tpOut 'partial.json') @{results=@($results)};Write-Output ('Deleted reviewed targets '+$index+'/'+$tpTargets.Count)}
 }
 $after=(Get-PSDrive C).Free
 Write-TpJson (Join-Path $tpOut 'result.json') @{schema='exact-twinpulse-retention-result-1.0';before_free_bytes=$before;after_free_bytes=$after;observed_free_increase_bytes=($after-$before);results=@($results);pins=$tpPins;remote=$tpProof;recovery='Current/pinned packages and raw evidence preserved; obsolete EXE bytes are not promised recoverable. Exact owned resource blobs/maps retained.'}
 Write-Output ([ordered]@{stage='COMPLETE';removed=@($results|Where-Object status -eq 'REMOVED').Count;failed=@($results|Where-Object status -eq 'FAILED').Count;free_after=$after;observed_recovery=($after-$before)}|ConvertTo-Json -Compress)
}finally{try{$tpLock.Unlock(0,1)}finally{$tpLock.Dispose()}}
