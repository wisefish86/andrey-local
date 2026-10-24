@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

python "Миграция через WinSCP.py" --apply-links
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Все доступные ссылки проверены, WOAS прописаны.
) else if "%RC%"=="2" (
    echo Часть файлов ещё не доступна по HTTPS.
    echo Загрузи недостающие через WinSCP и запусти этот BAT ещё раз.
) else (
    echo Операция завершилась с ошибкой ^(код %RC%^).
)

echo.
pause
exit /b %RC%
