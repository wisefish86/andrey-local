@echo off
chcp 65001 >nul
setlocal
title Andrey Local - Install Auto Sync
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Установить автосинхронизацию.ps1"
if errorlevel 1 (
  echo.
  echo Installation failed. Check the error above.
  pause
  exit /b 1
)
echo.
echo Auto synchronization schedule installed. Check Task Scheduler.
pause
