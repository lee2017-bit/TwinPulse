# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [string]$IsaacRoot = "C:\isaacsim"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$extensions = Join-Path $repoRoot "extensions"
$launcher = Join-Path $IsaacRoot "isaac-sim.bat"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Isaac Sim launcher not found: $launcher"
}

& $launcher --ext-folder $extensions --enable twinpulse.extension

