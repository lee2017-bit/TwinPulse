@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_twinpulse.ps1" -Launch
set "TWINPULSE_EXIT=%ERRORLEVEL%"
if not "%TWINPULSE_EXIT%"=="0" (
  echo.
  echo TwinPulse installation or launch failed. Read the error above.
  pause
)
exit /b %TWINPULSE_EXIT%
