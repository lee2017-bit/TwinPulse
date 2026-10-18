@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check_robot_connection.ps1"
pause
