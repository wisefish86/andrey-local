@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Автосинхронизация.ps1"
if errorlevel 1 (
 echo Automatic synchronization run failed.
 pause
 exit /b 1
)
echo Completed. Check .auto-sync.log at the repository root.
pause
