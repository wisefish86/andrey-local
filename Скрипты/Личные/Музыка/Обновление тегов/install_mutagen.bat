@echo off
where py >nul 2>nul
if %errorlevel%==0 (
    py -m pip install mutagen
) else (
    python -m pip install mutagen
)
pause
