@echo off
setlocal

REM Если папку не передали аргументом - подсказка пользователю
if "%~1"=="" (
    echo Перетащи папку заказа мышкой на этот файл
    echo или запусти так:
    echo   prepare_print.bat "Имя папки"
    echo.
    pause
    exit /b
)

REM Папка заказа (то, что перетянули или передали)
set "TARGET_FOLDER=%~1"

REM Папка, где лежат prepare_print.bat и prepare_print.py
set "SCRIPT_DIR=%~dp0"

echo SCRIPT_DIR:   %SCRIPT_DIR%
echo TARGET_FOLDER:%TARGET_FOLDER%
echo.

python "%SCRIPT_DIR%prepare_print.py" "%TARGET_FOLDER%"

if errorlevel 1 (
    echo.
    pause
)