@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    goto python_found
)

where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto python_found
)

echo Python was not found.
echo Install Python from https://www.python.org/downloads/
echo During installation, enable "Add python.exe to PATH".
echo Then install dependencies with:
echo python -m pip install PySide6 mutagen
pause
exit /b 1

:python_found
%PYTHON_CMD% -c "import PySide6, mutagen" >nul 2>nul
if errorlevel 1 (
    echo Required libraries are missing.
    echo Installing PySide6 and mutagen...
    echo.
    %PYTHON_CMD% -m pip install --user PySide6 mutagen
    if errorlevel 1 (
        echo.
        echo Library installation failed.
        echo Check your internet connection and the error above.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% -c "import PySide6, mutagen" >nul 2>nul
if errorlevel 1 (
    echo Libraries were installed but cannot be imported by this Python.
    pause
    exit /b 1
)

%PYTHON_CMD% "mp3_lyrics_gui.py"

:result
if errorlevel 1 (
    echo.
    echo The program ended with an error.
    echo Install the required libraries with:
    echo py -m pip install PySide6 mutagen
    echo or:
    echo python -m pip install PySide6 mutagen
    echo.
    pause
)
endlocal
