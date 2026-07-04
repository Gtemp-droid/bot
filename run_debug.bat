@echo off
cd /d "C:\Users\MAISON\Documents\Bot"
echo [%date% %time%] Starting proxy... > proxy_debug.log
"C:\Users\MAISON\AppData\Local\Programs\Python\Python312\python.exe" proxy.py >> proxy_debug.log 2>&1
echo [%date% %time%] Proxy exited with code %ERRORLEVEL% >> proxy_debug.log
if "%ERRORLEVEL%" NEQ "0" (
    echo Proxy failed. Check proxy_debug.log for details.
    pause
)
