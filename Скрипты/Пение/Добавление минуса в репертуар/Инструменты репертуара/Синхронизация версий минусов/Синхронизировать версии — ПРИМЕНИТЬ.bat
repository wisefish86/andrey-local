@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 "%~dp0sync_versions.py" --apply
set CODE=%ERRORLEVEL%
echo.
pause
exit /b %CODE%
