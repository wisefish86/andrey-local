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
echo   ЭКСПОРТ ТЕГОВ ДЛЯ GPT
echo   MP3 не изменяются
echo ============================================================
echo.

%PY% "id3_json_roundtrip.py" export
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
    echo Экспорт завершён без ошибок.
) else (
    echo Исправь ошибки чтения перед импортом отредактированного JSON.
)
echo.
pause
exit /b %EXITCODE%
