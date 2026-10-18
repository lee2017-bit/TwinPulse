@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
setlocal
cd /d "%~dp0"
if exist "%~dp0active-release.json" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_twinpulse_installed.ps1"
) else if exist "%~dp0release-manifest.json" (
  echo Run Install-Offline.cmd first, then use the Start-TwinPulse.cmd in the installed folder.
  exit /b 1
) else if exist "%LOCALAPPDATA%\TwinPulse\installed\active-release.json" (
  rem Normal user entry always follows the same installed Electron release.
  rem Use Start-TwinPulse-Development.cmd explicitly for source development.
  call "%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse.cmd"
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_twinpulse_app.ps1" -SkipBuild
)
set "TWINPULSE_EXIT=%ERRORLEVEL%"
if not "%TWINPULSE_EXIT%"=="0" (
  echo.
  echo TwinPulse could not start. Read the error above.
  pause
)
exit /b %TWINPULSE_EXIT%
