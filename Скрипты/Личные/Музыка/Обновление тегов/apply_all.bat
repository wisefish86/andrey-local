@echo off
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py update_tags.py --apply
) else (
    python update_tags.py --apply
)

echo.
pause
