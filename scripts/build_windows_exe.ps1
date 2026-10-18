# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$BuildPython = '')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $BuildPython) { $BuildPython = Join-Path $repoRoot '.build-venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $BuildPython)) {
    throw 'Project-local build environment is missing; see docs/WINDOWS_EXE_BUILD.md.'
}
& $BuildPython (Join-Path $PSScriptRoot 'build_windows_exe.py') --output-dir $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Windows EXE build failed; the previous output is preserved.' }
