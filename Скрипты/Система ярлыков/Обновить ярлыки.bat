@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Обновить-ярлыки.ps1" %*
if errorlevel 1 (
  echo.
  echo Shortcut update failed.
  pause
)
