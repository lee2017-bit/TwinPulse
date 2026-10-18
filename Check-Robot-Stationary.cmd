@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo TwinPulse Python environment is missing. Nothing was started.
  pause
  exit /b 2
)
".venv\Scripts\python.exe" "scripts\prepare_robot.py" --mode stationary --open-report %*
set "TP_STATIONARY_EXIT=%errorlevel%"
pause
exit /b %TP_STATIONARY_EXIT%
