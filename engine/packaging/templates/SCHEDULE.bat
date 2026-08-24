@echo off
rem ============================================================
rem  __DISPLAY_NAME__ - automatic updates
rem  Double-click this file once to have the report update itself
rem  on a schedule, even while this folder is closed - as long as
rem  you are signed in to this computer. Nothing is installed and
rem  nothing is sent anywhere.
rem ============================================================
setlocal
title __DISPLAY_NAME__ - automatic updates
cd /d "%~dp0"

for %%A in ("%~dp0.") do set "PKGNAME=%%~nxA"
set "TASKNAME=UltimateExcelAutomation - %PKGNAME%"
set "PYW=%~dp0Application\runtime\pythonw.exe"
set "LAUNCH=%~dp0Application\app\launch.py"

if not exist "%PYW%" goto :broken
if not exist "%LAUNCH%" goto :broken

:menu
echo.
echo   __DISPLAY_NAME__ - automatic updates
echo.
echo   This lets the report update itself on a schedule, without you
echo   opening this folder or pressing anything.
echo.
echo   1. Update every hour
echo   2. Update once a day
echo   3. Turn off automatic updates
echo   4. Cancel, change nothing
echo.
set "CHOICE="
set /p "CHOICE=Type a number (1-4) and press Enter: "

if "%CHOICE%"=="1" goto :hourly
if "%CHOICE%"=="2" goto :daily
if "%CHOICE%"=="3" goto :remove
if "%CHOICE%"=="4" goto :cancelled
echo.
echo   Please type 1, 2, 3 or 4.
goto :menu

:hourly
schtasks /create /tn "%TASKNAME%" /tr "\"%PYW%\" \"%LAUNCH%\" --run-once" /sc HOURLY /mo 1 /f >nul
goto :report

:daily
set "ATTIME="
set /p "ATTIME=What time each day, as HH:MM (24-hour) - e.g. 08:00: "
if "%ATTIME%"=="" set "ATTIME=08:00"
schtasks /create /tn "%TASKNAME%" /tr "\"%PYW%\" \"%LAUNCH%\" --run-once" /sc DAILY /st "%ATTIME%" /f >nul
goto :report

:remove
schtasks /delete /tn "%TASKNAME%" /f >nul 2>&1
echo.
echo   Automatic updates are now off.
echo   You can still open this folder and press START.bat any time to
echo   update by hand.
echo.
pause
exit /b 0

:report
if errorlevel 1 goto :failed
echo.
echo   Done. __DISPLAY_NAME__ will now update itself in the background.
echo   You do not need to keep this window, or this folder, open.
echo.
echo   To change this later, double-click SCHEDULE.bat again.
echo.
pause
exit /b 0

:failed
echo.
echo   The automatic schedule could not be set up on this computer.
echo.
echo   You can still update the report any time by opening this folder
echo   and pressing START.bat.
echo.
echo   Support code: E-RUN-003
echo.
pause
exit /b 1

:cancelled
exit /b 0

:broken
echo.
echo   This copy of __DISPLAY_NAME__ is incomplete.
echo.
echo   What to do: delete this folder, extract the original ZIP again,
echo   and double-click SCHEDULE.bat once more.
echo.
echo   Support code: E-PKG-001
echo.
pause
exit /b 1
