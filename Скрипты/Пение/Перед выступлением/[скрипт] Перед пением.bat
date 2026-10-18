@echo off
chcp 65001 >nul

echo Запуск скрипта "Перед пением"...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0[скрипт] Перед пением.ps1"

if %errorlevel% neq 0 (
    echo.
    echo Ошибка при выполнении скрипта "Перед пением".
    pause
    exit /b
)

echo.
echo Запуск удаления символа ֎ из названий файлов...
call "%~dp0[скрипт] Удалить из названия файлов ֎ если они в подпапках.bat"

echo.
echo Готово.