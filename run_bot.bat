@echo off
title Dofus HarvestBot
cd /d "%~dp0"

if "%1"=="--help" goto :help
if "%1"=="/?" goto :help
if "%1"=="-h" goto :help

echo.
echo === Dofus 1.29 HarvestBot ===
echo.
if "%1"=="" (
    echo Starting harvesting...
    echo Press Ctrl+C to stop.
    echo.
    "C:\Users\MAISON\AppData\Local\Programs\Python\Python312\python.exe" -m bot.main
) else (
    "C:\Users\MAISON\AppData\Local\Programs\Python\Python312\python.exe" -m bot.main %*
)
if errorlevel 1 pause
goto :eof

:help
echo Dofus 1.29 HarvestBot
echo.
echo Commands:
echo   run_bot              Start harvesting
echo   run_bot --dry-run    Scan only, no clicks
echo   run_bot --calibrate  Open calibration
echo   run_bot --log-level DEBUG  Verbose
echo.
pause
