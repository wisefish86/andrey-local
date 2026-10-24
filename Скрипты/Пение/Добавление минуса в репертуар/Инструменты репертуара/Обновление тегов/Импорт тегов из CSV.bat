@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "CSV=%~1"

if "%CSV%"=="" (
    for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='CSV (*.csv)|*.csv|Все файлы (*.*)|*.*'; $d.Title='Выбери CSV с тегами'; if($d.ShowDialog() -eq 'OK'){$d.FileName}"`) do set "CSV=%%F"
)

if "%CSV%"=="" (
    echo CSV не выбран.
    pause
    exit /b 1
)

if not exist "%CSV%" (
    echo CSV не найден:
    echo %CSV%
    pause
    exit /b 2
)

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
    %PY% -m pip install mutagen
    if errorlevel 1 (
        echo Не удалось установить Mutagen.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo 1/2. ПРОВЕРКА CSV БЕЗ ИЗМЕНЕНИЯ MP3
echo ============================================================
echo.

%PY% "src\import_tags.py" --check --csv "%CSV%" --config "config\tag_mapping.json"
if errorlevel 1 (
    echo.
    echo Проверка не прошла. Ничего не изменено.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Проверка прошла успешно.
echo 1 - ЗАПИСАТЬ ИЗМЕНЕНИЯ В MP3
echo 2 - ОТМЕНА
echo ============================================================
choice /C 12 /N /M "Выбор: "
if errorlevel 2 (
    echo.
    echo Отменено. MP3 не изменены.
    pause
    exit /b 0
)

echo.
echo ============================================================
echo 2/2. ЗАПИСЬ ТЕГОВ
echo ============================================================
echo.

%PY% "src\import_tags.py" --apply --csv "%CSV%" --config "config\tag_mapping.json"
if errorlevel 1 (
    echo.
    echo Импорт завершился с ошибкой. Смотри сообщение выше.
    pause
    exit /b 1
)

echo.
echo Готово. Импорт тегов завершён без ошибок.
pause
