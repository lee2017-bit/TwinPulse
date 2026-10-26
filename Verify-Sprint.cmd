@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
rem Test gate before any build (scripts\verify_sprint.py): required suites fully green, no new
rem failures elsewhere against outputs\verify-sprint\baseline.json. Writes outputs\verify-sprint\latest.json;
rem scripts\build_windows_exe.py refuses to build without a fresh PASS for the committed HEAD.
rem   Verify-Sprint.cmd                 full run
rem   Verify-Sprint.cmd --set-baseline  full run that records its core/provider/integration failures as the baseline
rem   Verify-Sprint.cmd --steps integration_robot_path,robot_safety_test_prefix   quick partial run (no latest.json)
setlocal
cd /d "%~dp0"
set "TWINPULSE_PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "TWINPULSE_PY=%~dp0.venv\Scripts\python.exe"
"%TWINPULSE_PY%" -B "%~dp0scripts\verify_sprint.py" %*
set "TWINPULSE_EXIT=%ERRORLEVEL%"
if not "%TWINPULSE_EXIT%"=="0" (
  echo.
  echo Sprint gate did not PASS. See outputs\verify-sprint\latest.json and the step logs beside it.
)
exit /b %TWINPULSE_EXIT%
