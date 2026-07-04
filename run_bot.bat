@echo off
title Dofus HarvestBot
cd /d "%~dp0"

if "%1"=="--help" goto :help
if "%1"=="/?" goto :help
if "%1"=="-h" goto :help

echo.
echo === Dofus 1.29 HarvestBot ===
echo.
"C:\Users\MAISON\AppData\Local\Programs\Python\Python312\python.exe" -m bot.main %*
if errorlevel 1 pause
goto :eof

:help
echo Dofus 1.29 HarvestBot
echo.
echo Usage: run_bot [options]
echo.
echo Options:
echo   --profile NAME     Use saved profile (e.g. --profile wheat)
echo   --list-profiles    Show available profiles
echo   --dry-run          Scan only, no clicks
echo   --calibrate        Open calibration
echo   --capture-templates  Capture action button images
echo   --log-level DEBUG  Verbose output
echo.
echo Examples:
echo   run_bot --profile wheat
echo   run_bot --profile wood --dry-run
echo   run_bot --calibrate
echo   run_bot --list-profiles
echo.
pause
