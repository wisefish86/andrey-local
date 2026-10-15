@echo off
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -m pip install mutagen
    if errorlevel 1 (
        echo Failed to install mutagen.
        pause
        exit /b 1
    )
    py update_tags.py --check
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found.
        echo Install Python and enable Add Python to PATH.
        pause
        exit /b 1
    )
    python -m pip install mutagen
    if errorlevel 1 (
        echo Failed to install mutagen.
        pause
        exit /b 1
    )
    python update_tags.py --check
)

echo.
pause
