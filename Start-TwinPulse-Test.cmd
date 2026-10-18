@echo off
rem SPDX-License-Identifier: Apache-2.0
rem TwinPulse - https://github.com/lee2017-bit/TwinPulse
if not exist "%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse-Test.cmd" (
  echo Install the current TwinPulse Windows package first.
  exit /b 1
)
call "%LOCALAPPDATA%\TwinPulse\installed\Start-TwinPulse-Test.cmd"
