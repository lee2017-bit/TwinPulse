@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo TwinPulse Python environment is missing. No robot operation attempted.
  pause
  exit /b 2
)
echo Running all four offline contract gates. No SSH, sensor, motor or deployment.
".venv\Scripts\python.exe" "scripts\rehearse_robot_demo_offline.py"
set "TP_REHEARSAL_EXIT=%errorlevel%"
pause
exit /b %TP_REHEARSAL_EXIT%
