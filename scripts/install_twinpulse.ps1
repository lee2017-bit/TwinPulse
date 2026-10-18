# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [string]$IsaacRoot = "",
    [switch]$Launch,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "apps\twinpulse-web"
$venvRoot = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$runtimeLock = Join-Path $repoRoot "config\python-runtime-requirements.lock"

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)" }
}

function Find-IsaacRoot([string]$Requested) {
    $candidates = if ($Requested) { @($Requested) } else { @(
        "C:\isaacsim",
        "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
    ) }
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath (Join-Path $candidate "python.bat")) -and
            (Test-Path -LiteralPath (Join-Path $candidate "isaac-sim.bat"))) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    if ($Requested -or $CheckOnly -or -not [Environment]::UserInteractive) {
        throw "Isaac Sim 6.0.1 standalone root not found. Run with -IsaacRoot <folder containing python.bat and isaac-sim.bat>."
    }
    $entered = Read-Host "Isaac Sim 6.0.1 folder (contains python.bat and isaac-sim.bat)"
    if (-not $entered -or -not (Test-Path -LiteralPath (Join-Path $entered "python.bat")) -or
        -not (Test-Path -LiteralPath (Join-Path $entered "isaac-sim.bat"))) {
        throw "Isaac Sim root is invalid: $entered"
    }
    return (Resolve-Path -LiteralPath $entered).Path
}

Push-Location $repoRoot
try {
    if (-not (Test-Path -LiteralPath $runtimeLock)) { throw "Python dependency lock is missing: $runtimeLock" }
    if (-not (Test-Path -LiteralPath (Join-Path $webRoot "pnpm-lock.yaml"))) {
        throw "Web dependency lock is missing"
    }
    $resolvedIsaacRoot = Find-IsaacRoot $IsaacRoot
    Write-Host "Isaac Sim: $resolvedIsaacRoot"

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)"
        Assert-LastExitCode "CPython 3.12 check"
        $createVenv = { & py -3.12 -m venv $venvRoot }
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw "CPython 3.12 is required (py -3.12 or python on PATH)." }
        & python -c "import sys; assert sys.version_info[:2] == (3, 12)"
        Assert-LastExitCode "CPython 3.12 check"
        $createVenv = { & python -m venv $venvRoot }
    }

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) { throw "Node.js is required. Install Node.js 20.19+ or 22.12+ and rerun this file." }
    & node -e "const [major,minor]=process.versions.node.split('.').map(Number); if (!((major===20&&minor>=19)||(major===22&&minor>=12)||major>=24)) process.exit(1)"
    Assert-LastExitCode "Node.js version check (20.19+ or 22.12+)"

    $pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
    if ($pnpmCommand) {
        $pnpmVersion = (& pnpm --version).Trim()
        Assert-LastExitCode "pnpm version check"
        if ($pnpmVersion -notmatch '^\d+\.\d+\.\d+$' -or [int]($pnpmVersion.Split('.')[0]) -lt 10) {
            $pnpmCommand = $null
        }
    }
    if (-not $pnpmCommand -and -not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm or pnpm is required with Node.js."
    }
    if ($CheckOnly) {
        Write-Host "TWINPULSE_INSTALL_CHECK=PASS"
        return
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host "Creating repository-local Python environment..."
        & $createVenv
        Assert-LastExitCode "Python virtual environment creation"
    }
    & $venvPython -c "import sys; assert sys.version_info[:2] == (3, 12)"
    Assert-LastExitCode "Repository Python version check"
    Write-Host "Installing hash-locked Python runtime dependency..."
    & $venvPython -m pip install --disable-pip-version-check --require-hashes -r $runtimeLock
    Assert-LastExitCode "Python runtime dependency installation"

    Write-Host "Installing lockfile-pinned web dependencies..."
    if ($pnpmCommand) {
        & pnpm --dir $webRoot install --frozen-lockfile
        Assert-LastExitCode "pnpm install"
        & pnpm --dir $webRoot build
        Assert-LastExitCode "React production build"
    } else {
        & npm exec --yes --package=pnpm@11.19.0 -- pnpm --dir $webRoot install --frozen-lockfile
        Assert-LastExitCode "pinned pnpm install"
        & npm exec --yes --package=pnpm@11.19.0 -- pnpm --dir $webRoot build
        Assert-LastExitCode "React production build"
    }
    Write-Host "Installing lockfile-pinned project-only desktop dependencies..."
    Push-Location (Join-Path $repoRoot 'apps\twinpulse-desktop')
    try {
        & npm.cmd ci --no-audit --no-fund
        Assert-LastExitCode "Electron desktop dependencies"
        # Some developer machines disable npm lifecycle scripts globally.
        # Install only the pinned official Electron runtime in this project.
        & node node_modules/electron/install.js
        Assert-LastExitCode "Pinned Electron runtime"
    } finally { Pop-Location }
    Write-Host "TWINPULSE_INSTALL_RESULT=PASS"
    Write-Host "API key is not part of this installer. Configure it in the local App."
    $localRuntime = Join-Path $repoRoot ".runtime"
    New-Item -ItemType Directory -Path $localRuntime -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $localRuntime "isaac-root.txt") -Value $resolvedIsaacRoot -Encoding UTF8

    if ($Launch) {
        & $venvPython scripts\twinpulse_launcher.py --isaac-root $resolvedIsaacRoot
        Assert-LastExitCode "TwinPulse launch"
    }
} finally {
    Pop-Location
}
