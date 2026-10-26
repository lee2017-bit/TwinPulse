# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
# Sprint test gate: every suite the sprint touches, in one command, with a receipt the build checks.
# Nothing here installs packages, touches the robot, Isaac or the network.
param(
    [string]$PythonExecutable = "",
    [switch]$SkipWeb,
    [switch]$SkipIntegration
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$repoPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = if ($PythonExecutable) { $PythonExecutable } elseif (Test-Path -LiteralPath $repoPython) { $repoPython } else { "python" }
$runId = Get-Date -Format "yyyyMMddTHHmmssZ"
$outDir = Join-Path $repoRoot "outputs\verify-sprint\$runId"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$head = (& git -C $repoRoot rev-parse HEAD 2>$null)
$dirty = ((& git -C $repoRoot status --porcelain --untracked-files=no 2>$null) | Measure-Object).Count -gt 0

$steps = @(
    @{ name = "compileall"; argv = @($python, "-B", "-m", "compileall", "-q", "packages", "scripts") },
    @{ name = "core"; argv = @($python, "-B", "-m", "unittest", "discover", "-s", "packages\twinpulse_core\tests", "-p", "test_*.py") },
    @{ name = "provider"; argv = @($python, "-B", "-m", "unittest", "discover", "-s", "packages\twinpulse_provider\tests", "-p", "test_*.py") },
    @{ name = "robot_safety_test_prefix"; argv = @($python, "-B", "-m", "unittest", "discover", "-s", "packages\twinpulse_robot_safety\tests", "-p", "test_*.py") },
    @{ name = "robot_safety_test_suffix"; argv = @($python, "-B", "-m", "unittest", "discover", "-s", "packages\twinpulse_robot_safety\tests", "-p", "*_test.py") }
)
if (-not $SkipIntegration) {
    $steps += @{ name = "integration"; argv = @($python, "-B", "-m", "unittest", "discover", "-s", "tests\integration", "-p", "test_*.py") }
}
if (-not $SkipWeb) {
    $pnpm = if (Get-Command pnpm.cmd -ErrorAction SilentlyContinue) { "pnpm.cmd" } else { "pnpm" }
    $steps += @{ name = "web"; argv = @($pnpm, "--dir", "apps\twinpulse-web", "test") }
}

$results = @()
$allPassed = $true
Push-Location $repoRoot
try {
    foreach ($step in $steps) {
        $log = Join-Path $outDir ($step.name + ".log")
        $started = Get-Date
        Write-Host ("== " + $step.name + ": " + ($step.argv -join " "))
        & $step.argv[0] $step.argv[1..($step.argv.Length - 1)] 2>&1 | Tee-Object -FilePath $log | Out-Host
        $code = $LASTEXITCODE
        $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
        $results += @{ name = $step.name; exit_code = $code; seconds = $seconds; log = $log }
        if ($code -ne 0) { $allPassed = $false; Write-Host ("!! " + $step.name + " FAILED (exit " + $code + ")") }
    }
} finally {
    Pop-Location
}

$receipt = @{
    schema = "twinpulse-sprint-gate-1.0"
    run_id = $runId
    head = $head
    dirty = $dirty
    finished_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    status = $(if ($allPassed) { "PASS" } else { "FAIL" })
    steps = $results
}
$json = $receipt | ConvertTo-Json -Depth 5
Set-Content -LiteralPath (Join-Path $outDir "receipt.json") -Value $json -Encoding UTF8
Set-Content -LiteralPath (Join-Path $repoRoot "outputs\verify-sprint\latest.json") -Value $json -Encoding UTF8
Write-Host ("Sprint gate " + $receipt.status + " at " + $head + $(if ($dirty) { " (dirty tree)" } else { "" }) + " -> " + $outDir)
if ($allPassed) { exit 0 } else { exit 1 }
