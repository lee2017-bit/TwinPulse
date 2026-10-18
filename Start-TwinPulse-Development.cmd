@echo off
rem SPDX-License-Identifier: Apache-2.0
rem Explicit source-development entry; not installed-user acceptance.
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_twinpulse_app.ps1" -SkipBuild
exit /b %ERRORLEVEL%
