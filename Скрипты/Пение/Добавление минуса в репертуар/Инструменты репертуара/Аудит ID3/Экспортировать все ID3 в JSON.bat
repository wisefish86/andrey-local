@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python не найден.
        echo Установи Python и включи Add Python to PATH.
        pause
        exit /b 1
    )
    set "PY=python"
)

%PY% -c "import mutagen" >nul 2>nul
if errorlevel 1 (
    echo Mutagen не установлен. Устанавливаю...
    %PY% -m pip install --user mutagen
    if errorlevel 1 (
        echo Не удалось установить Mutagen.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo   ПОДРОБНЫЙ АУДИТ ВСЕХ ID3 В JSON
echo   MP3 не изменяются
echo ============================================================
echo.

%PY% "export_all_id3.py"
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo Экспорт завершён без ошибок.
) else (
    echo Проверь ошибки чтения в подробном аудите. Этот JSON не подходит для GPT-импорта.
)
echo.
pause
exit /b %EXITCODE%
