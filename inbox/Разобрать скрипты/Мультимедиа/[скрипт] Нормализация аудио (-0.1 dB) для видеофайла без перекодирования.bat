@echo off
setlocal

if "%~1"=="" (
  echo Перетащи видеофайл на этот .bat
  pause
  exit /b
)

set "input=%~1"
set "output=%~dpn1_norm%~x1"

ffmpeg -i "%input%" -map 0:v -map 0:a -c:v copy -af alimiter=limit=-0.1dB "%output%"

echo.
echo Готово:
echo %output%
pause
