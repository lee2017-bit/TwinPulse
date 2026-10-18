# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'TwinPulse Python environment is missing. Run Install-TwinPulse first.'
    exit 2
}
& $python (Join-Path $PSScriptRoot 'check_robot_connection.py') --open-report
exit $LASTEXITCODE
