@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0\.."

set "MODE=%~1"
set "CSV=%~2"

if "%MODE%"=="" (
    echo Не указан режим check/apply.
    pause
    exit /b 2
)

if "%CSV%"=="" (
    for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='CSV (*.csv)|*.csv|Все файлы (*.*)|*.*'; $d.Title='Выбери CSV с тегами'; if($d.ShowDialog() -eq 'OK'){$d.FileName}"`) do set "CSV=%%F"
)

if "%CSV%"=="" (
    echo CSV не выбран.
    exit /b 1
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

if /i "%MODE%"=="check" (
    %PY% "src\import_tags.py" --check --csv "%CSV%" --config "config\tag_mapping.json"
) else if /i "%MODE%"=="apply" (
    %PY% "src\import_tags.py" --apply --csv "%CSV%" --config "config\tag_mapping.json"
) else (
    echo Неизвестный режим: %MODE%
    pause
    exit /b 2
)

echo.
pause
