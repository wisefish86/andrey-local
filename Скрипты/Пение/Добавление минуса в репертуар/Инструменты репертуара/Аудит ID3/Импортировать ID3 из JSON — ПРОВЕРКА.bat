@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "JSON_FILE=%~1"
if not defined JSON_FILE (
    echo Перетащи отредактированный JSON в окно консоли и нажми Enter.
    echo Или запусти этот BAT, перетащив JSON на его значок.
    set /p "JSON_FILE=Путь к JSON: "
)
set "JSON_FILE=%JSON_FILE:"=%"
if not exist "%JSON_FILE%" (
    echo ОШИБКА: файл JSON не найден: %JSON_FILE%
    pause
    exit /b 2
)
echo.
echo ПРОВЕРКА: исходные MP3 не изменяются.
echo.
py -3 "id3_json_roundtrip.py" import --json "%JSON_FILE%"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Обнаружены ошибки: проверь JSON-отчёт в data\reports.
pause
exit /b %RESULT%
