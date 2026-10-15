@echo off
setlocal

if "%~1"=="" (
    echo Перетащи папку заказа мышкой на этот файл
    echo.
    pause
    exit /b
)

set "TARGET_FOLDER=%~1"
set "SCRIPT_DIR=%~dp0"

echo SCRIPT_DIR:   %SCRIPT_DIR%
echo TARGET_FOLDER:%TARGET_FOLDER%
echo.

python "%SCRIPT_DIR%archive.py" "%TARGET_FOLDER%"

if errorlevel 1 (
    echo.
    pause
)