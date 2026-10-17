@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Backup.ps1" -ShowReport
set "rc=%errorlevel%"
echo.
if not "%rc%"=="0" echo Backup finished with error code %rc%
pause
exit /b %rc%
