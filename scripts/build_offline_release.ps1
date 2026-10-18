# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [string]$OutputRoot = "",
    [string]$ReleaseId = "",
    [switch]$AllowDirty,
    [string]$OfflineWheelPath = "",
    [switch]$ReuseBuiltWeb,
    [switch]$RequirePublicReview
)

$ErrorActionPreference = "Stop"
if ($ReuseBuiltWeb -and -not $OfflineWheelPath) {
    throw "-ReuseBuiltWeb requires a locally available hash-pinned -OfflineWheelPath; no downloads are allowed in this mode"
}
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $repoRoot "artifacts\offline-release" }
$repoRoot = (Resolve-Path -LiteralPath $repoRoot).Path
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$revision = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $revision -notmatch '^[a-f0-9]{40}$') { throw "A Git commit is required for a release" }
$dirty = [bool]((& git -C $repoRoot status --porcelain).Count)
if ($dirty -and -not $AllowDirty) { throw "Working tree has changes. Commit reviewed source first, or use -AllowDirty only for local testing." }
if (-not $ReleaseId) { $ReleaseId = "tp-" + $revision.Substring(0, 12) + $(if ($dirty) { "-dev" } else { "" }) }
if ($ReleaseId -notmatch '^[a-zA-Z0-9._-]{1,80}$') { throw "Invalid release ID" }
$releaseRoot = Join-Path $OutputRoot $ReleaseId
if (Test-Path -LiteralPath $releaseRoot) { throw "Release already exists: $releaseRoot" }

if (-not $ReuseBuiltWeb) {
    $pnpmVersion = (& pnpm --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $pnpmVersion -ne "11.19.0") { throw "pnpm 11.19.0 is required for a frozen release build" }
    if ($OfflineWheelPath) {
        & pnpm --dir (Join-Path $repoRoot "apps\twinpulse-web") install --offline --frozen-lockfile
    } else {
        & pnpm --dir (Join-Path $repoRoot "apps\twinpulse-web") install --frozen-lockfile
    }
    if ($LASTEXITCODE -ne 0) { throw "Frozen web install failed" }
    & pnpm --dir (Join-Path $repoRoot "apps\twinpulse-web") build
    if ($LASTEXITCODE -ne 0) { throw "Web build failed" }
}

function Copy-ReleaseFile([string]$Relative) {
    $source = Join-Path $repoRoot $Relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Required release source missing: $Relative" }
    $target = Join-Path $releaseRoot $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
foreach ($relative in @(
    "LICENSE", "NOTICE", "CITATION.cff", "THIRD_PARTY_NOTICES.md", "docs\LICENSING.md",
    "docs\RELEASE_PROVENANCE.md",
    "extensions\twinpulse.extension\LICENSE", "extensions\twinpulse.extension\NOTICE",
    "packages\twinpulse_robot_safety\LICENSE", "packages\twinpulse_robot_safety\NOTICE",
    "Install-Offline.cmd", "Start-TwinPulse.cmd",
    "scripts\install_twinpulse_offline.ps1", "scripts\start_twinpulse_installed.ps1",
    "scripts\twinpulse_launcher.py", "scripts\twinpulse_backend.py",
    "scripts\twinpulse_engine_host.py", "scripts\twinpulse_capture_contract.py",
    "scripts\inspect_robot_evidence.py", "scripts\ros_message_diagnostics.py",
    "packages\twinpulse_robot_safety\raw_ros_record.py",
    "config\python-runtime-requirements.lock",
    "extensions\twinpulse.extension\config\extension.toml",
    "docs\COMPANY_PC_INSTALL.md", "docs\QUICKSTART.md"
)) { Copy-ReleaseFile $relative }
foreach ($relativeRoot in @(
    "packages\twinpulse_core\src", "packages\twinpulse_provider\src",
    "packages\twinpulse_app\src", "extensions\twinpulse.extension\twinpulse",
    "scripts", "tests", "packages\twinpulse_core\tests", "packages\twinpulse_provider\tests", "packages\twinpulse_robot_safety"
)) {
    Get-ChildItem -LiteralPath (Join-Path $repoRoot $relativeRoot) -Recurse -File -Filter "*.py" | ForEach-Object {
        if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point in release source: $($_.FullName)" }
        Copy-ReleaseFile $_.FullName.Substring($repoRoot.Length + 1)
    }
}
# The product readiness action runs the existing four-gate local rehearsal before
# any SSH. Ship its tests and the same source/profile that the collector bundles;
# omitting these made the installed UI's button fail before robot contact.
Get-ChildItem -LiteralPath (Join-Path $repoRoot "packages\twinpulse_robot_safety") -Recurse -File | Where-Object {
    $_.Extension -in @('.json', '.cpp', '.hpp', '.txt', '.patch', '.md', '.sh') -and
    -not ($_.FullName -match '[\\/](build|checks|__pycache__)[\\/]')
} | ForEach-Object {
    if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point in robot source: $($_.FullName)" }
    Copy-ReleaseFile $_.FullName.Substring($repoRoot.Length + 1)
}
$distRoot = Join-Path $repoRoot "apps\twinpulse-web\dist"
# Portable, already pinned visual assets; never package private room photos or
# saved hardware captures. The project importer verifies these nine hashes.
$burgerRoot = "artifacts\robot-models\burger-isaac\usd\turtlebot3_burger_1"
foreach ($name in @("turtlebot3_burger.usda", "payloads\base.usda", "payloads\geometries.usd",
    "payloads\instances.usda", "payloads\materials.usda", "payloads\robot.usda",
    "payloads\Physics\mujoco.usda", "payloads\Physics\physics.usda", "payloads\Physics\physx.usda")) {
    Copy-ReleaseFile (Join-Path $burgerRoot $name)
}
Copy-ReleaseFile "artifacts\robot-models\turtlebot3-source\LICENSE"
Copy-ReleaseFile "artifacts\robot-models\burger-prepared\source.json"
$nominalRoot = "artifacts\robot-models\turtlebot3-source\turtlebot3_description"
foreach ($name in @("urdf\turtlebot3_burger.urdf", "meshes\bases\burger_base.stl",
    "meshes\wheels\left_tire.stl", "meshes\wheels\right_tire.stl", "meshes\sensors\lds.stl")) {
    Copy-ReleaseFile (Join-Path $nominalRoot $name)
}
# Fixed browser acceptance drivers use an explicitly selected EXISTING
# Playwright runtime. node_modules is not shipped or installed by verification.
Copy-ReleaseFile "apps\twinpulse-web\e2e\packaged-mission-isaac.mjs"
Copy-ReleaseFile "apps\twinpulse-web\e2e\startup-failure-real.mjs"
if (-not (Test-Path -LiteralPath (Join-Path $distRoot "index.html"))) { throw "Built UI is missing" }
Get-ChildItem -LiteralPath $distRoot -Recurse -File | ForEach-Object {
    if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point in web build" }
    Copy-ReleaseFile $_.FullName.Substring($repoRoot.Length + 1)
}
# Include canonical notices even when an older local dist is reused.
foreach ($name in @("LICENSE", "NOTICE")) {
    $target = Join-Path $releaseRoot ("apps\twinpulse-web\dist\" + $name)
    Copy-Item -LiteralPath (Join-Path $repoRoot $name) -Destination $target
}

$wheelhouse = Join-Path $releaseRoot "wheelhouse"
New-Item -ItemType Directory -Path $wheelhouse -Force | Out-Null
if ($OfflineWheelPath) {
    $wheel = [IO.Path]::GetFullPath($OfflineWheelPath)
    $lock = Get-Content -LiteralPath (Join-Path $repoRoot "config\python-runtime-requirements.lock") -Raw
    if ($lock -notmatch '(?m)^Pillow==12\.3\.0 --hash=sha256:([a-f0-9]{64})\s*$') {
        throw "Offline Pillow lock entry is missing or changed"
    }
    $expectedWheelHash = $Matches[1]
    if (-not (Test-Path -LiteralPath $wheel -PathType Leaf) -or
        [IO.Path]::GetFileName($wheel) -ne 'pillow-12.3.0-cp312-cp312-win_amd64.whl' -or
        ((Get-Item -LiteralPath $wheel).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedWheelHash) {
        throw "Offline Pillow wheel is missing, unpinned, or has a different hash"
    }
    Copy-Item -LiteralPath $wheel -Destination $wheelhouse
} else {
    & py -3.12 -m pip download --disable-pip-version-check --only-binary=:all: --no-deps --require-hashes -r (Join-Path $repoRoot "config\python-runtime-requirements.lock") --dest $wheelhouse
    if ($LASTEXITCODE -ne 0) { throw "Hash-locked Windows CPython 3.12 wheel download failed" }
}
$wheelFiles = @(Get-ChildItem -LiteralPath $wheelhouse -File)
if ($wheelFiles.Count -ne 1 -or $wheelFiles[0].Name -notmatch '^pillow-12\.3\.0-cp312-cp312-win_amd64\.whl$') {
    throw "Expected exactly one Windows x64 CPython 3.12 Pillow wheel"
}

# This is an offline metadata/content check, not legal or publication approval.
# No original assets/evidence are removed or rewritten to manufacture a PASS.
$auditArgs = @((Join-Path $repoRoot "scripts\audit_release_provenance.py"),
    "--wheel", $wheelFiles[0].FullName, "--release-root", $releaseRoot,
    "--output", (Join-Path $releaseRoot "provenance-audit.json"))
if ($RequirePublicReview) { $auditArgs += "--require-public" }
& py -3.12 @auditArgs
if ($LASTEXITCODE -ne 0) {
    if ($RequirePublicReview -and $LASTEXITCODE -eq 2) {
        throw "Public release requires content-specific rights/privacy review; see provenance-audit.json. Local package is preserved, not approved or published."
    }
    throw "Offline provenance inventory failed; no release PASS is issued."
}

$files = @(Get-ChildItem -LiteralPath $releaseRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($releaseRoot.Length + 1).Replace('\', '/')
        bytes = [long]$_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
})
$manifest = [ordered]@{
    schema = "twinpulse-offline-release-1.0"
    release_id = $ReleaseId
    git_revision = $revision
    dirty = $dirty
    platform = "win_amd64-cp312"
    public_release_status = "REQUIRES_CONTENT_SPECIFIC_REVIEW_NOT_PUBLICATION_APPROVAL"
    files = $files
}
if ($ReuseBuiltWeb) {
    # This copies and hashes the current reviewed dist. It does NOT prove a
    # clean source rebuild, and never installs dependencies or downloads wheels.
    $manifest["web_build_mode"] = "REUSED_EXISTING_DIST_NOT_REBUILT"
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "release-manifest.json") -Encoding UTF8
$bytes = (Get-ChildItem -LiteralPath $releaseRoot -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host "TWINPULSE_OFFLINE_RELEASE=PASS path=$releaseRoot files=$($files.Count) bytes=$bytes dirty=$dirty"
