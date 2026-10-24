@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 "Миграция плюсов на FTP.py" --apply
set EXITCODE=%ERRORLEVEL%
echo.
if "%EXITCODE%"=="0" (
    echo Миграция завершена. Проверь отчёт в ..\..\data\migration_plus_links
) else (
    echo Миграция остановлена с ошибкой ^(код %EXITCODE%^).
    echo Уже обработанные файлы сохранены. Проверь apply-отчёт в ..\..\data\migration_plus_links
)
echo.
pause
exit /b %EXITCODE%
