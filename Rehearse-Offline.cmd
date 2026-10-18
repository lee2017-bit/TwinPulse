@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\rehearse_offline_app.ps1"
set "TWINPULSE_REHEARSAL_EXIT=%ERRORLEVEL%"
echo.
echo Offline rehearsal finished. Results are under artifacts\offline-rehearsal-*.
echo This does not start or test the robot or Isaac.
pause
exit /b %TWINPULSE_REHEARSAL_EXIT%
