@echo off
chcp 65001 >nul
echo IPv4 addresses of this computer:
ipconfig | findstr /i "IPv4"
echo.
pause
