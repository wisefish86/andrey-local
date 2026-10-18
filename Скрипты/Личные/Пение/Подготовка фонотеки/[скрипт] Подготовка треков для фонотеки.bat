@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion

if "%~1"=="" goto NOFILES

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%%~n0.ps1"

if not exist "%PS1%" goto NOPS1

set "TEMP_FILE=%TEMP%\fonoteka_files_%RANDOM%_%RANDOM%.txt"
break > "%TEMP_FILE%"

:LOOP
if "%~1"=="" goto RUN

<nul set /p "=%~1" >> "%TEMP_FILE%"
echo.>> "%TEMP_FILE%"

shift
goto LOOP

:RUN
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -NoExit -File "%PS1%" -FileListPath "%TEMP_FILE%"
del "%TEMP_FILE%" 2>nul
pause
exit /b

:NOFILES
echo Перетащи mp3-файлы на BAT.
pause
exit /b

:NOPS1
echo Не найден PS1 рядом с BAT:
echo "%PS1%"
pause
exit /b 1