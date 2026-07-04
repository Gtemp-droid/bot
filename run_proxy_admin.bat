@echo off
cd /d "C:\Users\MAISON\Documents\Bot"
echo ========================================
echo  Dofus 1.29 MITM Proxy
echo  Starting proxy as admin...
echo ========================================
echo.
echo Output will be captured in proxy_output.txt
echo.
C:\Users\MAISON\AppData\Local\Programs\Python\Python312\python.exe proxy.py > proxy_output.txt 2>&1
echo Proxy exited with code %ERRORLEVEL%
pause
