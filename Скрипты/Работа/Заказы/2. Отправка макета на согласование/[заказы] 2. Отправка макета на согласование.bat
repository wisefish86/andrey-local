@echo off
setlocal

if "%~1"=="" (
    echo Перетащи папку заказа мышкой на этот файл
    echo или запусти так:
    echo   send_for_approval.bat "Имя папки"
    echo.
    pause
    exit /b
)

set "TARGET_FOLDER=%~1"
set "SCRIPT_DIR=%~dp0"

python "%SCRIPT_DIR%send_for_approval.py" "%TARGET_FOLDER%"

if errorlevel 1 (
    echo.
    pause
)