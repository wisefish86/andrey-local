@echo off
chcp 65001 >nul
set "SCRIPT_PATH=D:\YandexDisk\Ресурсы\Автоматизация\Скрипты\Все скрипты\Для пения и личные\[скрипт] Мониторинг папок.ps1"

echo Запуск PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PATH%"

if %errorlevel% neq 0 (
    echo.
    echo Скрипт завершился с ошибкой. Проверьте вывод выше.
    pause
) else (
    echo.
    echo Скрипт выполнен успешно.
    timeout /t 2 /nobreak >nul
)