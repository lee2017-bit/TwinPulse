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
    $isaacPython = Join-Path $IsaacRoot "python.bat"
    $r1TestPython = if (Test-Path -LiteralPath $isaacPython) { $isaacPython } else { "python" }
    python -m compileall -q packages extensions\twinpulse.extension\twinpulse scripts
    if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

    python packages\twinpulse_core\tests\test_contracts.py
    if ($LASTEXITCODE -ne 0) { throw "core tests failed" }

    python packages\twinpulse_provider\tests\test_provider.py
    if ($LASTEXITCODE -ne 0) { throw "provider tests failed" }

    & $r1TestPython -B -m unittest discover -s tests\integration -p test_r1_workflow.py
    if ($LASTEXITCODE -ne 0) { throw "R1 integration tests failed" }

    python scripts\verify_r3_application.py
    if ($LASTEXITCODE -ne 0) { throw "R3 application-service tests failed" }

    if (-not $SkipIsaac) {
        if (-not (Test-Path -LiteralPath $isaacPython)) {
            throw "Isaac Sim Python launcher not found: $isaacPython"
        }
        $env:TWINPULSE_ARTIFACT_DIR = $artifactDir
        $m1Output = & $isaacPython -B scripts\verify_m1_extension.py 2>&1
        $m1ExitCode = $LASTEXITCODE
        $m1Output | ForEach-Object { Write-Output $_ }
        $m1Pass = $m1Output | Select-String -SimpleMatch '"status": "PASS"'
        if ($m1ExitCode -ne 0 -or -not $m1Pass) { throw "Isaac M1/M2 acceptance failed" }

        $r2Output = & $isaacPython -B scripts\verify_r2_stage_identity.py 2>&1
        $r2ExitCode = $LASTEXITCODE
        $r2Output | ForEach-Object { Write-Output $_ }
        $r2Error = $r2Output | Select-String -SimpleMatch 'R2 ERROR:'
        $r2Pass = $r2Output | Select-String -SimpleMatch 'R2 SAFETY PASS:'
        if ($r2ExitCode -ne 0 -or $r2Error -or -not $r2Pass) {
            throw "Isaac R2 stage identity/safety acceptance failed"
        }
    }

    $manifest = [ordered]@{
        status = "PASS"
        run_id = $runId
        created_at = (Get-Date).ToString("o")
        app = "PASS_R3"
        isaac = if ($SkipIsaac) { "NOT_RUN" } else { "PASS_M1_M2_R2_R3_LEGACY" }
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
