@echo off
setlocal

REM Если ничего не передали аргументом - подсказка пользователю
if "%~1"=="" (
    echo Перетащи папку заказа, архив или файл/файлы мышкой на этот файл "[заказы] 1. Начало работы"
    echo.
    pause
    exit /b
)

REM Папка, где лежат rename.py
set "SCRIPT_DIR=%~dp0"

echo SCRIPT_DIR: %SCRIPT_DIR%
echo.

REM Передаем в Python все перетянутые элементы, а не только первый
python "%SCRIPT_DIR%rename.py" %*

REM Если произошла ошибка (код возврата 1 и выше) - ждем нажатия клавиши
if errorlevel 1 (
    echo.
    pause
)
REM При успехе окно закроется автоматически
