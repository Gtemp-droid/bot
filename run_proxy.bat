@echo off
title Dofus 1.29 MITM Proxy
cd /d "C:\Users\MAISON\Documents\Bot"
echo ========================================
echo  Dofus 1.29 MITM Proxy
echo  Target: 57.129.113.60:5557
echo ========================================
echo.
echo Make sure the game client is running!
echo.
echo This will intercept game traffic and log packets.
echo The game will disconnect and reconnect through the proxy.
echo.
pause
echo Starting proxy...
python proxy.py
pause
