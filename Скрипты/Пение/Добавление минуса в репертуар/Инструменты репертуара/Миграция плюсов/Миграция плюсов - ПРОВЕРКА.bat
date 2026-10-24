@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 "Миграция плюсов на FTP.py"
set EXITCODE=%ERRORLEVEL%

set "REPORT=%~dp0..\..\data\migration_plus_links\ПРОБЛЕМНЫЕ ПАПКИ.txt"

echo.
echo Dry-run завершён.
if exist "%REPORT%" (
  echo Открываю список проблемных папок:
  echo %REPORT%
  start "" notepad.exe "%REPORT%"
) else (
  echo Отчёт проблемных папок не найден:
  echo %REPORT%
)
echo.
pause
exit /b %EXITCODE%
