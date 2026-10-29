@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Проверка раскладки для Syncthing — без изменения файлов...
py -3 "Разложить минусы по статусам для телефона.py"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Обнаружены ошибки — см. отчёт.
pause
exit /b %RESULT%
