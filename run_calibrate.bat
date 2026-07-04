@echo off
title Dofus HarvestBot - Calibration
echo Starting calibration mode
echo Make sure Dofus is running and visible.
echo.
"C:\Users\MAISON\AppData\Local\Programs\Python\Python312\python.exe" -m bot.main --calibrate
if errorlevel 1 (
    echo.
    pause
)
