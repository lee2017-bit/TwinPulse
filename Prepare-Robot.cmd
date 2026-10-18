@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo TwinPulse Python environment is missing. Nothing was installed or started.
  pause
  exit /b 2
)
".venv\Scripts\python.exe" "scripts\prepare_robot.py" --open-report %*
set "TP_PREPARE_EXIT=%errorlevel%"
pause
exit /b %TP_PREPARE_EXIT%
