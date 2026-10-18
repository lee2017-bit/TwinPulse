# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param([Parameter(Mandatory=$true)][string]$OutputDirectory, [switch]$Apply)
$ErrorActionPreference='Stop'
$tpRepo=(Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$tpInstalled=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'TwinPulse/installed'))
$tpReleaseRoot=Join-Path $tpInstalled 'releases'
$tpRoots=@((Join-Path $tpRepo 'outputs'),(Join-Path $tpRepo 'artifacts'),$tpReleaseRoot)
$tpOutput=[IO.Path]::GetFullPath($OutputDirectory)
if(-not $tpOutput.StartsWith((Join-Path $tpRepo 'outputs')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'OUTPUT_OUTSIDE_REVIEWED_ROOT'}
if(Test-Path -LiteralPath $tpOutput){throw 'NEW_OUTPUT_DIRECTORY_REQUIRED'}
$tpPins=@('20261018T060740Z-eb840a4afcaa','20261018T044930Z-d0d4e62d6701','20261018T054101Z-10f256a1732a')
$tpProofPath=Join-Path $tpRepo 'outputs/github-preservation-20261018/remote-verification.json'
$tpProof=Get-Content -LiteralPath $tpProofPath -Raw | ConvertFrom-Json
if($tpProof.status -ne 'REMOTE_SOURCE_AND_ARCHIVE_VERIFIED' -or -not $tpProof.private -or $tpProof.repository -ne 'lee2017-bit/TwinPulse'){throw 'REMOTE_PRESERVATION_REQUIRED'}
$tpRemote=(& git -C $tpRepo ls-remote origin refs/heads/main) -split '\s+'
if($LASTEXITCODE -ne 0 -or $tpRemote[0] -ne $tpProof.source_commit){throw 'REMOTE_PRESERVATION_HEAD_CHANGED'}
if(-not ($tpProof.assets | Where-Object {$_.download_verified -and $_.sha256 -eq 'b40e498fc19eda8b045152c92cddc91def3b90f824e047146a47f01bc1f1dd8f'})){throw 'REMOTE_ROLLBACK_ARCHIVE_REQUIRED'}

function Assert-TpPlainBoundPath([string]$Path) {
    $tpFull=[IO.Path]::GetFullPath($Path)
    $tpScope=$tpRoots | Where-Object {$tpFull.StartsWith($_+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)} | Select-Object -First 1
    if(-not $tpScope -or $tpFull -eq $tpScope){throw 'DELETE_TARGET_OUTSIDE_REVIEWED_ROOT'}
    $tpWalk=$tpFull
    while($tpWalk){
        if((Get-Item -LiteralPath $tpWalk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_PATH_REFUSED'}
        $tpParent=Split-Path -Parent $tpWalk
        if(-not $tpParent -or $tpParent -eq $tpWalk){break};$tpWalk=$tpParent
    }
    return $tpFull
}
function Write-TpJson([string]$Path,$Value){$Value|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $Path -Encoding utf8}

New-Item -ItemType Directory -Path $tpOutput | Out-Null
$tpBefore=(Get-PSDrive -Name ([IO.Path]::GetPathRoot($tpRepo).Substring(0,1))).Free
$tpActive=Get-Content -LiteralPath (Join-Path $tpInstalled 'active-release.json') -Raw|ConvertFrom-Json
if($tpActive.release_id -notin $tpPins){throw 'ACTIVE_RELEASE_NOT_PINNED'}
$tpLock=$null
try {
    if($Apply){
        $tpLock=[IO.File]::Open((Join-Path (Split-Path -Parent $tpInstalled) 'maintenance.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
        if($tpLock.Length -eq 0){$tpLock.SetLength(1)}
        $tpLock.Lock(0,1)
    }
    $tpProcesses=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('TwinPulse.exe','TwinPulseDesktop.exe','kit.exe','python.exe','pythonw.exe')} | Select-Object ExecutablePath,CommandLine)
    $tpCandidates=[Collections.Generic.List[object]]::new()
    $tpProtected=[Collections.Generic.List[object]]::new()
    $tpRecords=Join-Path $tpOutput 'build-records';New-Item -ItemType Directory -Path $tpRecords|Out-Null
    function Add-TpTarget([string]$Path,[string]$Kind,[string]$BuildId){
        $tpAbsolute=Assert-TpPlainBoundPath $Path
        if($tpCandidates|Where-Object path -eq $tpAbsolute){return}
        if($tpProcesses|Where-Object {($_.ExecutablePath -and $_.ExecutablePath.StartsWith($tpAbsolute+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) -or ($_.CommandLine -and $_.CommandLine.IndexOf($tpAbsolute,[StringComparison]::OrdinalIgnoreCase) -ge 0)}){
            $tpProtected.Add([pscustomobject]@{path=$tpAbsolute;reason='RUNNING_PROCESS_REFERENCE'});return
        }
        $tpItem=Get-Item -LiteralPath $tpAbsolute -Force
        if($tpItem.PSIsContainer){
            if(Get-ChildItem -LiteralPath $tpAbsolute -Recurse -Directory -Force|Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}){throw 'REPARSE_CHILD_REFUSED'}
            $tpFiles=@(Get-ChildItem -LiteralPath $tpAbsolute -Recurse -File -Force)
        }else{$tpFiles=@($tpItem)}
        $tpCandidates.Add([pscustomobject]@{path=$tpAbsolute;kind=$Kind;build_id=$BuildId;bytes=($tpFiles|Measure-Object Length -Sum).Sum;files=$tpFiles.Count;directory=$tpItem.PSIsContainer})
    }
    foreach($tpRelease in Get-ChildItem -LiteralPath $tpReleaseRoot -Directory){
        if($tpRelease.Name -in $tpPins){$tpProtected.Add([pscustomobject]@{path=$tpRelease.FullName;reason='CURRENT_ROLLBACK_OR_REPRO_PIN'});continue}
        $tpManifest=Join-Path $tpRelease.FullName 'windows-release-manifest.json'
        if(-not (Test-Path -LiteralPath $tpManifest)){$tpProtected.Add([pscustomobject]@{path=$tpRelease.FullName;reason='UNCLASSIFIED_RELEASE_NO_MANIFEST'});continue}
        $tpM=Get-Content -LiteralPath $tpManifest -Raw|ConvertFrom-Json
        if($tpM.schema -ne 'twinpulse-windows-exe-1.0' -or $tpM.build_id -ne $tpRelease.Name){throw 'INSTALLED_RELEASE_IDENTITY_MISMATCH'}
        Copy-Item -LiteralPath $tpManifest -Destination (Join-Path $tpRecords ($tpM.build_id+'-windows-manifest.json'))
        $tpSource=Join-Path $tpRelease.FullName '_internal/resources/source-manifest.json'
        if(Test-Path -LiteralPath $tpSource){Copy-Item -LiteralPath $tpSource -Destination (Join-Path $tpRecords ($tpM.build_id+'-source-manifest.json'))}
        Add-TpTarget $tpRelease.FullName 'OBSOLETE_INSTALLED_RELEASE' $tpM.build_id
    }
    foreach($tpBuildScope in $tpRoots[0..1]){
        foreach($tpManifest in Get-ChildItem -LiteralPath $tpBuildScope -Recurse -File -Filter 'windows-release-manifest.json'){
            if($tpManifest.Directory.Name -ne 'TwinPulse' -or $tpManifest.Directory.Parent.Name -ne 'dist'){continue}
            $tpM=Get-Content -LiteralPath $tpManifest.FullName -Raw|ConvertFrom-Json
            if($tpM.schema -ne 'twinpulse-windows-exe-1.0'){continue}
            $tpBuildRoot=$tpManifest.Directory.Parent.Parent.FullName
            if($tpM.build_id -in $tpPins){$tpProtected.Add([pscustomobject]@{path=$tpBuildRoot;reason='CURRENT_ROLLBACK_OR_REPRO_PIN'});continue}
            Copy-Item -LiteralPath $tpManifest.FullName -Destination (Join-Path $tpRecords ($tpM.build_id+'-windows-manifest.json'))
            $tpSource=Join-Path $tpBuildRoot 'staging/resources/source-manifest.json'
            if(Test-Path -LiteralPath $tpSource){Copy-Item -LiteralPath $tpSource -Destination (Join-Path $tpRecords ($tpM.build_id+'-source-manifest.json'))}
            foreach($tpChild in @('dist','work','staging','desktop-build')){
                $tpTarget=Join-Path $tpBuildRoot $tpChild
                if(Test-Path -LiteralPath $tpTarget){Add-TpTarget $tpTarget 'REPRODUCIBLE_BUILD_INTERMEDIATE' $tpM.build_id}
            }
        }
        foreach($tpZip in Get-ChildItem -LiteralPath $tpBuildScope -Recurse -File -Filter 'TwinPulse-Windows-*.zip'){
            if($tpPins|Where-Object {$tpZip.Name.Contains($_)}){$tpProtected.Add([pscustomobject]@{path=$tpZip.FullName;reason='PINNED_ARCHIVE'});continue}
            Add-TpTarget $tpZip.FullName 'OBSOLETE_DISTRIBUTION_ZIP' ''
        }
    }
    $tpPlan=[ordered]@{schema='reviewed-build-prune-1.0';apply=[bool]$Apply;remote_commit=$tpProof.source_commit;remote_release=$tpProof.release_url;pins=$tpPins;active_release=$tpActive.release_id;before_free_bytes=$tpBefore;logical_candidate_bytes=($tpCandidates|Measure-Object bytes -Sum).Sum;targets=@($tpCandidates);protected=@($tpProtected);not_in_scope=@('runtime/projects','runtime/devices','settings','provider evidence','photos','raw recordings','original assets','Docker','Isaac','pagefile','source checkout')}
    Write-TpJson (Join-Path $tpOutput 'plan.json') $tpPlan
    Write-Output ([ordered]@{stage='PLAN';targets=$tpCandidates.Count;logical_bytes=$tpPlan.logical_candidate_bytes;protected=$tpProtected.Count;apply=[bool]$Apply}|ConvertTo-Json -Compress)
    if(-not $Apply){return}
    $tpResults=[Collections.Generic.List[object]]::new();$tpIndex=0
    foreach($tpTarget in $tpCandidates){
        $tpIndex++
        $tpAbsolute=Assert-TpPlainBoundPath $tpTarget.path
        try {
            # Each exact absolute target is within one reviewed output/release root.
            # Native PowerShell deletion only; no path enumeration crosses shells.
            Remove-Item -LiteralPath $tpAbsolute -Recurse -Force
            if(Test-Path -LiteralPath $tpAbsolute){throw 'TARGET_STILL_PRESENT'}
            $tpResults.Add([pscustomobject]@{path=$tpAbsolute;status='REMOVED';logical_bytes=$tpTarget.bytes})
        }catch{$tpResults.Add([pscustomobject]@{path=$tpAbsolute;status='FAILED';error_type=$_.Exception.GetType().Name})}
        if($tpIndex%15 -eq 0){Write-TpJson (Join-Path $tpOutput 'result.json') @{results=@($tpResults)};Write-Output ('{"stage":"DELETE","completed":'+$tpIndex+',"total":'+$tpCandidates.Count+'}')}
    }
    $tpAfter=(Get-PSDrive -Name ([IO.Path]::GetPathRoot($tpRepo).Substring(0,1))).Free
    Write-TpJson (Join-Path $tpOutput 'result.json') ([ordered]@{schema='reviewed-build-prune-result-1.0';before_free_bytes=$tpBefore;after_free_bytes=$tpAfter;observed_free_increase_bytes=($tpAfter-$tpBefore);results=@($tpResults);pins=$tpPins;source_commit=$tpProof.source_commit})
    Write-Output ([ordered]@{stage='COMPLETE';removed=@($tpResults|Where-Object status -eq 'REMOVED').Count;failed=@($tpResults|Where-Object status -eq 'FAILED').Count;after_free_bytes=$tpAfter;observed_free_increase_bytes=($tpAfter-$tpBefore)}|ConvertTo-Json -Compress)
} finally {if($tpLock){try{$tpLock.Unlock(0,1)}finally{$tpLock.Dispose()}}}
