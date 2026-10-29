@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Обновление копий для Syncthing. Оригиналы не изменяются.
echo Старые копии, созданные этим инструментом и не изменённые вручную, будут удалены.
py -3 "Разложить для телефона.py" --apply
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo Готово — папки для телефона обновлены.
) else (
  echo Ошибка — проверьте сообщения и JSON-отчёт. Syncthing проверьте перед синхронизацией.
)
pause
exit /b %RESULT%
