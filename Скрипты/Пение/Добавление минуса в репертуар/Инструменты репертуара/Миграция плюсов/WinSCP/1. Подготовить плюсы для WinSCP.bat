@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

py -3 "Миграция через WinSCP.py" --prepare --open-folder
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Пакет подготовлен.
    echo Загрузи ВСЕ MP3 из открывшейся папки через WinSCP.
    echo После загрузки запусти: 2. Прописать WOAS после WinSCP.bat
) else (
    echo Подготовка завершилась с ошибкой ^(код %RC%^).
)

echo.
pause
exit /b %RC%
