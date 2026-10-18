# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
param(
    [switch]$SkipIsaac,
    [switch]$RunR6,
    [string]$IsaacRoot = "C:\isaacsim",
    [string]$PythonExecutable = "",
    [string]$ArtifactDirectory = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$artifactDir = if ($ArtifactDirectory) { [IO.Path]::GetFullPath($ArtifactDirectory) } else { Join-Path $repoRoot "artifacts\runs\$runId" }
if ($ArtifactDirectory -and (Test-Path -LiteralPath $artifactDir)) {
    throw "Explicit artifact directory must be new; existing evidence will not be overwritten."
}
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
$transcriptStarted = $false
$repoPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$appPython = if ($PythonExecutable) {
    $PythonExecutable
} elseif (Test-Path -LiteralPath $repoPython) {
    $repoPython
} else {
    "python"
}

Push-Location $repoRoot
try {
    Start-Transcript -Path (Join-Path $artifactDir "verification-console.txt") -Force | Out-Null
    $transcriptStarted = $true
    $isaacPython = Join-Path $IsaacRoot "python.bat"
    $r1TestPython = if (Test-Path -LiteralPath $isaacPython) { $isaacPython } else { $appPython }
    & $appPython -c "import PIL; assert tuple(map(int, PIL.__version__.split('.')[:2])) >= (12, 2)"
    if ($LASTEXITCODE -ne 0) { throw "Pillow >=12.2 is required; install config\python-runtime-requirements.lock" }
    & $appPython -m compileall -q packages extensions\twinpulse.extension\twinpulse scripts
    if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

    & $appPython scripts\generate_engine_ts.py --check
    if ($LASTEXITCODE -ne 0) { throw "generated TypeScript engine contract is stale" }

    & $appPython -m unittest discover -s packages\twinpulse_core\tests -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "core tests failed" }

    & $appPython -m unittest -v tests.integration.test_scan_replay_cli tests.integration.test_robot_reports tests.integration.test_scan_review tests.integration.test_scan_archive tests.integration.test_derived_site_review tests.integration.test_derived_review_selection tests.integration.test_native_scan_review tests.integration.test_native_hour_summary tests.integration.test_four_hour_summary tests.integration.test_photo_scan_review tests.integration.test_lidar_recording_review tests.integration.test_offline_rehearsal_summary
    if ($LASTEXITCODE -ne 0) { throw "offline scan/report tests failed" }

    & $appPython -m unittest -v tests.integration.test_bedroom_twin tests.integration.test_bedroom_review tests.integration.test_bedroom_rehearsal tests.integration.test_robot_geometry_evidence tests.integration.test_room_localization_review
    if ($LASTEXITCODE -ne 0) { throw "photo bedroom draft tests failed" }

    & $appPython -B -m unittest -v tests.integration.test_robot_diagnostics tests.integration.test_robot_connection tests.integration.test_manual_controller tests.integration.test_physical_controller packages.twinpulse_robot_safety.tests.teleop_test packages.twinpulse_robot_safety.tests.stop_policy_test packages.twinpulse_robot_safety.tests.mission_test
    if ($LASTEXITCODE -ne 0) { throw "robot console offline tests failed" }

    & $appPython -m unittest discover -s packages\twinpulse_provider\tests -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "provider tests failed" }

    & $r1TestPython -B -m unittest discover -s tests\integration -p test_r1_workflow.py
    if ($LASTEXITCODE -ne 0) { throw "R1 integration tests failed" }

    & $appPython scripts\verify_r3_application.py
    if ($LASTEXITCODE -ne 0) { throw "R3 application-service tests failed" }

    & $appPython -B -m unittest -v tests.integration.test_r4_bridge_api tests.integration.test_http_rejection_delivery
    if ($LASTEXITCODE -ne 0) { throw "R4 loopback API/bridge contract tests failed" }

    & $appPython -B -m unittest -v tests.integration.test_r5_product_api tests.integration.test_s2a_input_integrity tests.integration.test_s2b_generation_ownership tests.integration.test_s2c_provider_settings tests.integration.test_s2d_managed_replay tests.integration.test_s3c_product_wiring
    if ($LASTEXITCODE -ne 0) { throw "R5 product API tests failed" }

    & $appPython -B -m unittest -v tests.integration.test_a2_project_isolation tests.integration.test_a2_room_recipe tests.integration.test_scene_edit_proposals tests.integration.test_a2_project_catalog tests.integration.test_h2b2_site_review
    if ($LASTEXITCODE -ne 0) { throw "A2 project/room and H2b2 saved-site review tests failed" }

    & $appPython -B -m unittest -v tests.integration.test_a4_m2d_evaluation tests.integration.test_a4_saved_provider_evaluation
    if ($LASTEXITCODE -ne 0) { throw "A4 stored evaluation tests failed" }

    $env:TWINPULSE_TEST_TMP = Join-Path $artifactDir "r6-process-manager-tests"
    & $appPython -B -m unittest -v tests.integration.test_r6_process_manager
    if ($LASTEXITCODE -ne 0) { throw "R6 process-manager tests failed" }

    pnpm --dir apps\twinpulse-web test
    if ($LASTEXITCODE -ne 0) { throw "R5 React tests failed" }

    pnpm --dir apps\twinpulse-web build
    if ($LASTEXITCODE -ne 0) { throw "R5 React production build failed" }

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

        $r4Output = & $isaacPython -B scripts\verify_r4_bridge.py 2>&1
        $r4ExitCode = $LASTEXITCODE
        $r4Output | ForEach-Object { Write-Output $_ }
        $r4Pass = $r4Output | Select-String -SimpleMatch 'TWINPULSE_R4_RESULT={"backend_loss_watchdog"'
        $r4Status = $r4Output | Select-String -SimpleMatch '"status": "PASS"'
        if ($r4ExitCode -ne 0 -or -not $r4Pass -or -not $r4Status) {
            throw "Isaac R4 managed bridge acceptance failed"
        }

        $r5Output = & $isaacPython -B scripts\verify_r5_web.py 2>&1
        $r5ExitCode = $LASTEXITCODE
        $r5Output | ForEach-Object { Write-Output $_ }
        $r5Pass = $r5Output | Select-String -SimpleMatch 'TWINPULSE_R5_RESULT={"actual_isaac"'
        $r5Status = $r5Output | Select-String -SimpleMatch '"status": "PASS"'
        if ($r5ExitCode -ne 0 -or -not $r5Pass -or -not $r5Status) {
            throw "R5 React browser to actual-Isaac acceptance failed"
        }

        if ($RunR6) {
            $r6ArtifactDir = Join-Path $artifactDir "r6-app"
            & $appPython scripts\verify_app_e2e.py --isaac-root $IsaacRoot --artifact-dir $r6ArtifactDir
            if ($LASTEXITCODE -ne 0) {
                throw "R6 managed-launcher browser/actual-Isaac acceptance failed"
            }
        }
    }

    $manifest = [ordered]@{
        status = "PASS"
        run_id = $runId
        created_at = (Get-Date).ToString("o")
        app = "PASS_R3_R4_R5_S2A_S2B_S2C_S2D_S3B_S3C_WIRING_CONTRACTS_REACT_BUILD_R6_PROCESS_MANAGER"
        isaac = if ($SkipIsaac) {
            "NOT_RUN"
        } elseif ($RunR6) {
            "PASS_M1_M2_R2_R3_LEGACY_R4_BRIDGE_R5_WEB_E2E_R6_MANAGED_APP_E2E"
        } else {
            "PASS_M1_M2_R2_R3_LEGACY_R4_BRIDGE_R5_WEB_E2E_R6_NOT_RUN"
        }
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
    Remove-Item Env:TWINPULSE_TEST_TMP -ErrorAction SilentlyContinue
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    Pop-Location
}
