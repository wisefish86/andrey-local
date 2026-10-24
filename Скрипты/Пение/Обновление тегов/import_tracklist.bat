@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "MODE=%~1"
set "CSV=%~2"

if "%MODE%"=="" (
    echo Не указан режим check/apply.
    exit /b 2
)

if "%CSV%"=="" set "CSV=%~dp0TrackList_ИТОГОВЫЙ_ДЛЯ_ИМПОРТА.csv"

if not exist "%CSV%" (
    echo CSV не найден:
    echo %CSV%
    echo.
    echo Перетащи итоговый CSV на нужный BAT
    echo или положи TrackList_ИТОГОВЫЙ_ДЛЯ_ИМПОРТА.csv рядом со скриптами.
    pause
    exit /b 2
)

where py >nul 2>nul
if %errorlevel%==0 (
    if /i "%MODE%"=="check" (
        py import_tracklist.py --check --csv "%CSV%"
    ) else (
        py import_tracklist.py --apply --csv "%CSV%"
    )
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python не найден.
        echo Установи Python и включи Add Python to PATH.
        pause
        exit /b 1
    )
    if /i "%MODE%"=="check" (
        python import_tracklist.py --check --csv "%CSV%"
    ) else (
        python import_tracklist.py --apply --csv "%CSV%"
    )
)

echo.
pause
