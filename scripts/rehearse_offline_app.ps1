# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$repoPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $repoPython)) { throw "Existing repository Python required. Nothing will be installed." }
$runId = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$outputDir = Join-Path $repoRoot "artifacts\offline-rehearsal-$runId"
New-Item -ItemType Directory -Path $outputDir | Out-Null
Push-Location $repoRoot
try {
    Write-Host "Offline regression + real local browser rehearsal. Synthetic inputs only; no robot/Isaac/provider calls."
    # Windows PowerShell treats unittest's ordinary stderr progress as an error
    # record. Capture it without terminating; the child exit code is authoritative.
    $ErrorActionPreference = "Continue"
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "verify_twinpulse.ps1") -SkipIsaac -ArtifactDirectory (Join-Path $outputDir "regression") 2>&1 |
            ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message }
                else { $_.ToString() }
            } |
            Tee-Object -FilePath (Join-Path $outputDir "regression.log")
        $verifyExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = "Stop"
    }
    if ($verifyExit -ne 0) { throw "Offline regression failed. Browser rehearsal not started. See $outputDir" }
    & $repoPython (Join-Path $PSScriptRoot "rehearse_offline_app.py") (Join-Path $outputDir "browser")
    if ($LASTEXITCODE -ne 0) { throw "Browser rehearsal failed. See $outputDir" }
    & $repoPython (Join-Path $PSScriptRoot "summarize_offline_rehearsal.py") $outputDir
    if ($LASTEXITCODE -ne 0) { throw "Evidence summary failed. See $outputDir" }
    Write-Host "OFFLINE_REHEARSAL=PASS results=$outputDir"
    Write-Host "Open the static evidence page: $(Join-Path $outputDir 'summary.html')"
} catch {
    # Preserve the original failure. The summary is diagnostic, never a retry.
    if (-not (Test-Path -LiteralPath (Join-Path $outputDir "summary.json"))) {
        & $repoPython (Join-Path $PSScriptRoot "summarize_offline_rehearsal.py") $outputDir
    }
    throw
} finally {
    Pop-Location
}
