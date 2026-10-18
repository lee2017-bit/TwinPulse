# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [string]$IsaacRoot = "",
    [int]$Port = -1,
    [string]$Browser = "",
    [string]$PythonExecutable = "",
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{0,63}$')][string]$ProjectId = "default",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "apps\twinpulse-web"
$savedIsaacRoot = Join-Path $repoRoot ".runtime\isaac-root.txt"
if (-not $IsaacRoot) {
    if (Test-Path -LiteralPath $savedIsaacRoot) {
        $IsaacRoot = (Get-Content -LiteralPath $savedIsaacRoot -Raw).Trim()
    } else {
        $IsaacRoot = "C:\isaacsim"
    }
}
$isaacPython = Join-Path $IsaacRoot "python.bat"
$repoPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$appPython = if ($PythonExecutable) {
    $PythonExecutable
} elseif (Test-Path -LiteralPath $repoPython) {
    $repoPython
} else {
    "python"
}

if (-not (Test-Path -LiteralPath $isaacPython)) {
    throw "Isaac Sim Python launcher not found: $isaacPython"
}

Push-Location $repoRoot
try {
    & $appPython -c "import PIL; assert tuple(map(int, PIL.__version__.split('.')[:2])) >= (12, 2)"
    if ($LASTEXITCODE -ne 0) {
        throw "TwinPulse Python image decoder is missing. Create .venv and install config\python-runtime-requirements.lock with --require-hashes."
    }
    if (-not $SkipBuild) {
        if (Get-Command pnpm -ErrorAction SilentlyContinue) {
            pnpm --dir $webRoot build
        } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
            npm exec --yes --package=pnpm@11.19.0 -- pnpm --dir $webRoot build
        } else {
            throw "Node.js and pnpm/npm are required. Run Install-TwinPulse.cmd first."
        }
        if ($LASTEXITCODE -ne 0) { throw "TwinPulse React production build failed" }
    } elseif (-not (Test-Path -LiteralPath (Join-Path $webRoot "dist\index.html"))) {
        throw "Built UI is missing. Run Install-TwinPulse.cmd first."
    }

    $arguments = @("scripts\twinpulse_launcher.py", "--isaac-root", $IsaacRoot, "--project-id", $ProjectId)
    if ($Port -ge 0) { $arguments += @('--port', "$Port") }
    if ($Browser) { $arguments += @("--browser", $Browser) }
    & $appPython @arguments
    if ($LASTEXITCODE -ne 0) { throw "TwinPulse launcher exited with code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
