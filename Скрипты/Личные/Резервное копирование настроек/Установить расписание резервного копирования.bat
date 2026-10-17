@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Установить расписание.ps1"
set "rc=%errorlevel%"
echo.
if not "%rc%"=="0" echo Error: installation failed. Code %rc%
if "%rc%"=="0" echo Schedule installed or updated.
pause
exit /b %rc%
