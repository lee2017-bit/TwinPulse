# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param([string]$InstallRoot = "", [switch]$Offline,
      [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,63}$')][string]$ProjectId = "default")

$ErrorActionPreference = "Stop"
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $PSScriptRoot }
$activeFile = Join-Path $InstallRoot "active-release.json"
if (-not (Test-Path -LiteralPath $activeFile)) { throw "TwinPulse is not installed. Run Install-Offline.cmd first." }
$active = Get-Content -LiteralPath $activeFile -Raw | ConvertFrom-Json
if ($active.schema -eq 'twinpulse-windows-install-1.0') {
    if ([string]$active.release_id -notmatch '^[A-Za-z0-9_-]{1,80}$' -or
        [string]$active.exe -ne ('releases/' + [string]$active.release_id + '/TwinPulse.exe')) {
        throw 'Invalid Windows EXE active release'
    }
    $exe = Join-Path $InstallRoot ([string]$active.exe)
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Installed TwinPulse.exe is missing' }
    $exeArgs = @('--project-id', $ProjectId)
    if ($Offline) { $exeArgs += '--offline' }
    & $exe @exeArgs
    return
}
if ([string]$active.release_id -notmatch '^[a-zA-Z0-9._-]{1,80}$') { throw "Invalid active release ID" }
$releaseRoot = Join-Path (Join-Path $InstallRoot "releases") ([string]$active.release_id)
$python = Join-Path $releaseRoot ".venv\Scripts\python.exe"
$launcher = Join-Path $releaseRoot "scripts\twinpulse_launcher.py"
$isaacRoot = [string]$active.isaac_root
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $launcher) -or
    -not (Test-Path -LiteralPath (Join-Path $isaacRoot "python.bat"))) {
    throw "Active release, Python, or Isaac Sim is missing. Re-run Install-Offline.cmd."
}
$launcherArgs = @($launcher, "--isaac-root", $isaacRoot, "--project-id", $ProjectId)
if ($Offline) { $launcherArgs += "--offline" }
& $python @launcherArgs
if ($LASTEXITCODE -ne 0) { throw "TwinPulse exited with code $LASTEXITCODE" }
