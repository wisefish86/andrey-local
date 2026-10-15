@echo off
setlocal
chcp 65001 >nul
set "builder=%~dp0PDF-сборщик.pyw"
if not exist "%builder%" (
    echo Не найден PDF-сборщик.pyw. Положите его рядом с этим файлом запуска.
    pause
    exit /b 1
)
where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pyw.exe -3 "%builder%" %*
    exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%builder%" %*
    exit /b
)
where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe -3 "%builder%" %*
    if errorlevel 1 pause
    exit /b
)
where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe "%builder%" %*
    if errorlevel 1 pause
    exit /b
)
echo Не найден Python. Установите Python 3.10 или новее с python.org.
echo При установке включите Python Launcher или Add Python to PATH.
pause
exit /b 1
