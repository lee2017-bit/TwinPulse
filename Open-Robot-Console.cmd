@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Existing TwinPulse Python environment is missing. Nothing installed.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -B "%~dp0scripts\launch_robot_console.py"
if errorlevel 1 pause
