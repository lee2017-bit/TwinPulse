param(
    [switch]$SkipIsaac,
    [string]$IsaacRoot = "C:\isaacsim"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$artifactDir = Join-Path $repoRoot "artifacts\runs\$runId"
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
$transcriptStarted = $false

Push-Location $repoRoot
try {
    Start-Transcript -Path (Join-Path $artifactDir "verification-console.txt") -Force | Out-Null
    $transcriptStarted = $true
    python -m compileall -q packages extensions\twinpulse.extension\twinpulse scripts
    if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

    python packages\twinpulse_core\tests\test_contracts.py
    if ($LASTEXITCODE -ne 0) { throw "core tests failed" }

    python packages\twinpulse_provider\tests\test_provider.py
    if ($LASTEXITCODE -ne 0) { throw "provider tests failed" }

    if (-not $SkipIsaac) {
        $isaacPython = Join-Path $IsaacRoot "python.bat"
        if (-not (Test-Path -LiteralPath $isaacPython)) {
            throw "Isaac Sim Python launcher not found: $isaacPython"
        }
        $env:TWINPULSE_ARTIFACT_DIR = $artifactDir
        & $isaacPython scripts\verify_m1_extension.py
        if ($LASTEXITCODE -ne 0) { throw "Isaac acceptance failed" }
    }

    $manifest = [ordered]@{
        status = "PASS"
        run_id = $runId
        created_at = (Get-Date).ToString("o")
        isaac = if ($SkipIsaac) { "NOT_RUN" } else { "PASS" }
        artifact_dir = $artifactDir
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $artifactDir "manifest.json") -Encoding UTF8
    Write-Output "TWINPULSE_VERIFY_RESULT=PASS artifact_dir=$artifactDir"
}
catch {
    $manifest = [ordered]@{
        status = "FAIL"
        run_id = $runId
        created_at = (Get-Date).ToString("o")
        error = $_.Exception.Message
        artifact_dir = $artifactDir
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $artifactDir "manifest.json") -Encoding UTF8
    Write-Error $_
    exit 1
}
finally {
    Remove-Item Env:TWINPULSE_ARTIFACT_DIR -ErrorAction SilentlyContinue
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    Pop-Location
}
