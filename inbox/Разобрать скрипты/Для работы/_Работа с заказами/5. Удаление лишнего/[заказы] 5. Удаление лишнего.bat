@echo off
setlocal

if "%~1"=="" (
    echo Перетащи папку заказа мышкой на этот файл
    echo или запусти так:
    echo   cleanup_order.bat "Имя папки"
    echo.
    pause
    exit /b
)

set "TARGET_FOLDER=%~1"
set "SCRIPT_DIR=%~dp0"

python "%SCRIPT_DIR%cleanup_order.py" "%TARGET_FOLDER%"

if errorlevel 1 (
    echo.
    pause
)