@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
rem Test gate before any build: core, provider, robot-safety, app integration and web tests.
rem Writes outputs\verify-sprint\latest.json; scripts\build_windows_exe.py refuses to build without a fresh PASS.
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\verify_sprint.ps1" %*
set "TWINPULSE_EXIT=%ERRORLEVEL%"
if not "%TWINPULSE_EXIT%"=="0" (
  echo.
  echo Sprint gate FAILED. Fix the failing suite before building; see outputs\verify-sprint\latest.json
)
exit /b %TWINPULSE_EXIT%
