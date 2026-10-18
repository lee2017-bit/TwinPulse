# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [string]$BundleRoot = "",
    [string]$InstallRoot = "",
    [string]$IsaacRoot = "",
    [switch]$CheckOnly,
    [switch]$AllowDevelopment,
    [switch]$IsolatedTest
)

$ErrorActionPreference = "Stop"
if (-not $BundleRoot) { $BundleRoot = Split-Path -Parent $PSScriptRoot }
if (-not $InstallRoot) { $InstallRoot = Join-Path $env:LOCALAPPDATA "TwinPulse\installed" }
$BundleRoot = (Resolve-Path -LiteralPath $BundleRoot).Path
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$manifestPath = Join-Path $BundleRoot "release-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "This is not a prepared offline release (manifest missing)." }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema -ne "twinpulse-offline-release-1.0" -or
    [string]$manifest.release_id -notmatch '^[a-zA-Z0-9._-]{1,80}$' -or
    $manifest.platform -ne "win_amd64-cp312" -or
    ($manifest.dirty -eq $true -and -not $AllowDevelopment)) {
    throw "Unrecognized or development-only release manifest"
}
$entries = @($manifest.files)
if ($entries.Count -lt 10 -or $entries.Count -gt 1000) { throw "Unexpected release file count" }
$seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $entries) {
    $relative = [string]$entry.path
    if ($relative -notmatch '^[A-Za-z0-9._/-]+$' -or $relative.StartsWith('/') -or
        $relative -match '(^|/)\.\.?(/|$)' -or $relative.Contains('//') -or
        -not $seen.Add($relative)) { throw "Unsafe or duplicate release path: $relative" }
    $source = Join-Path $BundleRoot ($relative.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Release file missing: $relative" }
    $item = Get-Item -LiteralPath $source
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Release reparse point forbidden: $relative" }
    if ($item.Length -ne [long]$entry.bytes -or
        (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$entry.sha256) {
        throw "Release hash mismatch: $relative"
    }
}
foreach ($required in @(
    "scripts/twinpulse_launcher.py", "scripts/twinpulse_backend.py", "scripts/twinpulse_engine_host.py",
    "scripts/twinpulse_capture_contract.py", "scripts/inspect_robot_evidence.py",
    "scripts/ros_message_diagnostics.py", "packages/twinpulse_robot_safety/raw_ros_record.py",
    "config/python-runtime-requirements.lock",
    "apps/twinpulse-web/dist/index.html", "extensions/twinpulse.extension/config/extension.toml"
)) { if (-not $seen.Contains($required)) { throw "Incomplete release: $required" } }
Write-Host "TWINPULSE_RELEASE_VERIFY=PASS release=$($manifest.release_id) files=$($entries.Count)"

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    & py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32"
    if ($LASTEXITCODE -ne 0) { throw "64-bit CPython 3.12 is required (py -3.12)." }
    $pythonCommand = "py"
} else {
    $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonPath) { throw "64-bit CPython 3.12 is required. Install it from an approved offline prerequisite." }
    & $pythonPath -c "import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32"
    if ($LASTEXITCODE -ne 0) { throw "64-bit CPython 3.12 is required." }
    $pythonCommand = $pythonPath
}
if (-not $IsaacRoot) {
    foreach ($candidate in @("C:\isaacsim", "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64")) {
        if (Test-Path -LiteralPath (Join-Path $candidate "python.bat")) { $IsaacRoot = $candidate; break }
    }
}
if (-not $IsaacRoot -and -not $CheckOnly) { $IsaacRoot = Read-Host "Isaac Sim 6.0.1 root folder (python.bat and isaac-sim.bat)" }
if ($IsaacRoot -and (-not (Test-Path -LiteralPath (Join-Path $IsaacRoot "python.bat")) -or
    -not (Test-Path -LiteralPath (Join-Path $IsaacRoot "isaac-sim.bat")))) {
    throw "Isaac Sim root is invalid: $IsaacRoot"
}
if ($CheckOnly) { Write-Host "TWINPULSE_OFFLINE_CHECK=PASS"; return }
if (-not $IsaacRoot) { throw "Isaac Sim 6.0.1 root is required" }
$IsaacRoot = (Resolve-Path -LiteralPath $IsaacRoot).Path
$launcherLock = Join-Path $env:LOCALAPPDATA "TwinPulse\runtime\launcher.lock"
if (Test-Path -LiteralPath $launcherLock) {
    $defaultInstallRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "TwinPulse\installed"))
    if (-not $IsolatedTest -or $InstallRoot.TrimEnd('\') -eq $defaultInstallRoot.TrimEnd('\')) {
        throw "A TwinPulse launcher is active or left a lock. Stop it normally and investigate the lock before installing."
    }
    try {
        $lockData = Get-Content -LiteralPath $launcherLock -Raw | ConvertFrom-Json
        $ownerPid = [int]$lockData.owner_pid
        if ($ownerPid -le 0 -or (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)) {
            throw "Launcher owner is active or unknown"
        }
    } catch {
        throw "Cannot prove launcher lock is stale; isolated installation refused."
    }
    Write-Host "TWINPULSE_ISOLATED_TEST=stale launcher lock retained; default installation untouched"
}
$releaseId = [string]$manifest.release_id
$releasesRoot = Join-Path $InstallRoot "releases"
$target = Join-Path $releasesRoot $releaseId
$staging = Join-Path $releasesRoot (".install-" + [Guid]::NewGuid().ToString("N"))
$releasePrefix = [IO.Path]::GetFullPath($releasesRoot).TrimEnd('\') + '\'
if (-not ([IO.Path]::GetFullPath($staging)).StartsWith($releasePrefix, [StringComparison]::OrdinalIgnoreCase) -or
    -not ([IO.Path]::GetFullPath($target)).StartsWith($releasePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Install target escaped the selected installation directory"
}
if (Test-Path -LiteralPath $target) { throw "This release is already installed. Existing files were not changed: $target" }
New-Item -ItemType Directory -Path $staging -Force | Out-Null
try {
    foreach ($entry in $entries) {
        $relative = ([string]$entry.path).Replace('/', '\')
        $destination = Join-Path $staging $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $BundleRoot $relative) -Destination $destination
    }
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $staging "release-manifest.json")
    $venv = Join-Path $staging ".venv"
    if ($pythonCommand -eq "py") { & py -3.12 -m venv $venv } else { & $pythonCommand -m venv $venv }
    if ($LASTEXITCODE -ne 0) { throw "Local virtual environment creation failed" }
    $venvPython = Join-Path $venv "Scripts\python.exe"
    & $venvPython -m pip install --disable-pip-version-check --no-index --find-links (Join-Path $staging "wheelhouse") --only-binary=:all: --require-hashes -r (Join-Path $staging "config\python-runtime-requirements.lock")
    if ($LASTEXITCODE -ne 0) { throw "Offline wheel install failed; no package index was contacted" }
    & $venvPython -c "import PIL; assert PIL.__version__ == '12.3.0'"
    if ($LASTEXITCODE -ne 0) { throw "Installed image decoder check failed" }
    Move-Item -LiteralPath $staging -Destination $target
    $active = [ordered]@{ release_id = $releaseId; isaac_root = $IsaacRoot }
    $activeTemp = Join-Path $InstallRoot ("active-release." + [Guid]::NewGuid().ToString("N") + ".tmp")
    $active | ConvertTo-Json | Set-Content -LiteralPath $activeTemp -Encoding UTF8
    $activePath = Join-Path $InstallRoot "active-release.json"
    if (Test-Path -LiteralPath $activePath) {
        [IO.File]::Replace($activeTemp, $activePath, (Join-Path $InstallRoot "active-release.previous.json"))
    } else {
        Move-Item -LiteralPath $activeTemp -Destination $activePath
    }
    Copy-Item -LiteralPath (Join-Path $target "Start-TwinPulse.cmd") -Destination (Join-Path $InstallRoot "Start-TwinPulse.cmd") -Force
    New-Item -ItemType Directory -Path (Join-Path $InstallRoot "scripts") -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $target "scripts\start_twinpulse_installed.ps1") -Destination (Join-Path $InstallRoot "scripts\start_twinpulse_installed.ps1") -Force
    Write-Host "TWINPULSE_OFFLINE_INSTALL=PASS release=$releaseId"
    Write-Host "Start here: $(Join-Path $InstallRoot 'Start-TwinPulse.cmd')"
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
