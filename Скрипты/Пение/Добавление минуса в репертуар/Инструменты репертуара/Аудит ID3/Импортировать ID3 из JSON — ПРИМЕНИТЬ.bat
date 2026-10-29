@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "JSON_FILE=%~1"
if not defined JSON_FILE set /p "JSON_FILE=Путь к исправленному JSON: "
set "JSON_FILE=%JSON_FILE:"=%"
if not exist "%JSON_FILE%" (
  echo Файл не найден.
  pause
  exit /b 2
)
py -3 "id3_json_roundtrip.py" import --json "%JSON_FILE%" --apply
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
