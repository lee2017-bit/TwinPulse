@echo off
rem SPDX-FileCopyrightText: 2026 Jaewon Lee
rem SPDX-License-Identifier: Apache-2.0
rem Source: https://github.com/lee2017-bit/TwinPulse
rem Physical link soak (default 10 min): needs the App started with Start-TwinPulse-Test.cmd (CDP), the operator present and the robot powered. No motion.
cd /d "%~dp0"
node scripts\soak_physical_link.mjs %1 %2 %3
pause
