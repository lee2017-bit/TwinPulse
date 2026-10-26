@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
rem Lists robot session directories whose PC copy is complete and older than 1 day; deletes them only after you type DELETE.
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\prune_robot_sessions.py" %*
pause
