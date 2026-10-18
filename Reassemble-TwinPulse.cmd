@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\reassemble_offline_release.ps1" -TransferRoot "%~dp0"
set "TWINPULSE_EXIT=%ERRORLEVEL%"
if not "%TWINPULSE_EXIT%"=="0" (
  echo.
  echo Reassembly failed. Check which numbered part is missing or corrupt.
  pause
)
exit /b %TWINPULSE_EXIT%
