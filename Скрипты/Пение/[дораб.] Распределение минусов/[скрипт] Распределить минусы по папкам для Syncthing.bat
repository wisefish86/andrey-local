@echo off
chcp 65001 >nul

cd /d "%~dp0"

echo.
echo ========================================
echo   Перенос папок из плейлистов MusicBee
echo ========================================
echo.
echo Текущая папка: %~dp0
echo.

set "PS1=%~dp0[скрипт] Распределить минусы по папкам для Syncthing.ps1"

if not exist "%PS1%" (
    echo [ОШИБКА] Не найден файл:
    echo %PS1%
    pause
    exit /b 1
)

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%PS1%"

echo.
pause