@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Синхронизация.ps1"
if errorlevel 1 (
 echo Synchronization failed.
 pause
 exit /b 1
)
pause
