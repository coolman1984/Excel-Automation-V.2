@echo off
rem ============================================================
rem  __DISPLAY_NAME__
rem  Double-click this file. The report opens in your browser.
rem  Nothing is installed and nothing is sent anywhere.
rem ============================================================
setlocal
title __DISPLAY_NAME__
cd /d "%~dp0"

set "APP=%~dp0Application"
set "PYW=%APP%\runtime\pythonw.exe"
set "PY=%APP%\runtime\python.exe"
set "LAUNCH=%APP%\app\launch.py"

if not exist "%LAUNCH%" goto :broken
if exist "%PYW%" goto :run_quiet
if exist "%PY%" goto :run_console
goto :broken

:run_quiet
start "" "%PYW%" "%LAUNCH%"
exit /b 0

:run_console
"%PY%" "%LAUNCH%"
exit /b %errorlevel%

:broken
echo.
echo   This copy of __DISPLAY_NAME__ is incomplete.
echo.
echo   What to do: delete this folder, extract the original ZIP again,
echo   and double-click START.bat once more.
echo.
echo   Support code: E-PKG-001
echo.
pause
exit /b 1
