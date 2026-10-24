@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 "Пересканировать репертуар для Singer Andrey.py"
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE%==0 (
  echo Репертуар для Singer Andrey обновлён.
) else (
  echo Перескан завершён с ошибками. Проверь вывод выше.
)
echo.
pause
exit /b %EXITCODE%
