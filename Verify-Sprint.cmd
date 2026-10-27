@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
rem Test gate before any build (scripts\verify_sprint.py): the required suites (compileall, robot safety, the robot-path
rem and regression integration modules, web vitest; about 10 min) must be fully green. Writes outputs\verify-sprint\latest.json;
rem scripts\build_windows_exe.py refuses to build without a fresh PASS for the committed HEAD (clean tree, 24 h).
rem The scripted functional pass of the installed App is the build chain's post-install acceptance step, not a gate step.
rem   Verify-Sprint.cmd                 required steps (before a build)
rem   Verify-Sprint.cmd --after-build   core/provider/full integration beside the install (about 55 min); compared with
rem                                     outputs\verify-sprint\baseline.json, writes after-build-latest.json, never blocks a build
rem   Verify-Sprint.cmd --after-build --set-baseline   records that run's failures as the new baseline
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
