@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_twinpulse_offline.ps1" -BundleRoot "%~dp0"
set "TWINPULSE_EXIT=%ERRORLEVEL%"
if not "%TWINPULSE_EXIT%"=="0" (
  echo.
  echo Offline installation failed. Read the error above; the previous active release is unchanged.
  pause
)
exit /b %TWINPULSE_EXIT%
