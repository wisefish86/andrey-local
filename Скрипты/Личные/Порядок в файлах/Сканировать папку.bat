@echo off
chcp 65001 >nul
set "ROOT=%~1"
if not defined ROOT (
  echo Перетащите папку на этот BAT-файл.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scan-Folder.ps1" -Root "%ROOT%"
if errorlevel 1 pause
