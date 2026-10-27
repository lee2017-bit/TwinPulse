@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
rem Lists old installed TwinPulse releases (dry run). Keeps the active release, the protected evidence builds and the
rem newest 3. Nothing is removed unless you pass --delete AND type DELETE. Never touches user data.
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\prune_old_builds.py" %*
pause
