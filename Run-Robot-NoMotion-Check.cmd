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
echo One no-motion readiness run: source preparation, idle check, 20-second passive collection.
echo This may deploy reviewed project source. It never commands movement or starts the LiDAR driver.
echo This is for odom/TF diagnosis, NOT the full demo or a four-stage physical test.
echo ROS LaserScan may be absent because the COIN driver is intentionally not started.
echo Torque OFF is not automatic. Use both explicit OFF/floor flags only when appropriate.
choice /C YN /N /M "Robot is available; start this single SSH/deployment/observation run? [Y/N] "
if errorlevel 2 exit /b 2
".venv\Scripts\python.exe" "scripts\run_robot_readiness.py" --run --open-report %*
set "TP_READINESS_EXIT=%errorlevel%"
pause
exit /b %TP_READINESS_EXIT%
