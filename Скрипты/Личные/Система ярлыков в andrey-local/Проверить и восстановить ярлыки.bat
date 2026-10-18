@echo off
chcp 65001 >nul
echo Shortcut diagnostic (no changes by default).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Проверить-и-восстановить-ярлыки.ps1" %*
echo.
pause
