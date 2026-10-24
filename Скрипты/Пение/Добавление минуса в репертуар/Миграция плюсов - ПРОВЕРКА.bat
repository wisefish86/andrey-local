@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 "Миграция плюсов на FTP.py"
set EXITCODE=%ERRORLEVEL%
echo.
echo Dry-run завершён. Отчёты лежат в data\migration_plus_links
echo.
pause
exit /b %EXITCODE%
