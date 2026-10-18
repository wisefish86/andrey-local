@echo off
setlocal
chcp 65001 >nul
set "NCONVERT=nconvert.exe"
where nconvert.exe >nul 2>nul
if errorlevel 1 (
  if exist "D:\System\Programs\NConvert\nconvert.exe" (
    set "NCONVERT=D:\System\Programs\NConvert\nconvert.exe"
  ) else (
    echo NConvert not found. Install NConvert or add it to PATH.
    pause
    exit /b 1
  )
)
if not exist "%~dp0!watermark.png" (
  echo Watermark not found next to BAT.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Drag image files onto this BAT or its shortcut.
  pause
  exit /b 1
)
:next
if "%~1"=="" goto done
"%NCONVERT%" -wmopacity 15 -wmflag center -wmfile "%~dp0!watermark.png" -out webp -q 75 "%~1"
if errorlevel 1 echo Conversion failed: %~1
shift
goto next
:done
echo Done.
pause
