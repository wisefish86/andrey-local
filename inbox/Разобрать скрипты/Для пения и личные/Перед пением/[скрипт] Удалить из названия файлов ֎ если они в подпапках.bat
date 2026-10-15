@echo off
chcp 65001 >nul

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0[скрипт] Удалить из названия файлов ֎ если они в подпапках.ps1"

if %errorlevel% neq 0 (
    echo.
    echo Скрипт завершился с ошибкой.
    pause
    exit /b
)

exit