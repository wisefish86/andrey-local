@echo off
chcp 65001 >nul
echo Проверяю состояние монозвука...
echo.

:: Чтение значения из реестра
for /f "tokens=3" %%a in ('reg query "HKCU\Software\Microsoft\Multimedia\Audio" /v AccessibilityMonoMixState 2^>nul ^| find "REG_DWORD"') do set MONO_RAW=%%a

if "%MONO_RAW%"=="" (
    echo Параметр не найден (монозвук выключен по умолчанию).
) else (
    set /a MONO=%MONO_RAW%
    echo Сырое значение: %MONO_RAW%
    echo Обработанное значение: %MONO%
)

echo.
pause