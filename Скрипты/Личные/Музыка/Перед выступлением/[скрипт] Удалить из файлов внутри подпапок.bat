@echo off
chcp 65001 >nul

echo Запуск PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0[скрипт] Перед пением.ps1"

if %errorlevel% neq 0 (
    echo.
    echo Скрипт завершился с ошибкой. Проверьте вывод выше.
    pause
) else (
    echo.
    echo Скрипт выполнен успешно.
    timeout /t 2 /nobreak >nul
)