@echo off
title Dofus HarvestBot - Character Calibration
echo Starting character detection calibration
echo Make sure Dofus is running and visible.
echo.
echo Adjust trackbars until the character is outlined in green.
echo.
"C:\Users\MAISON\AppData\Local\Programs\Python\Python312\python.exe" -m bot.main --calibrate-character
if errorlevel 1 (
    echo.
    pause
)
