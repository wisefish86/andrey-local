@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

if "%~1"=="" (
  echo Перетащите файлы или папки на этот bat.
  pause
  exit /b 1
)

:loop
if "%~1"=="" goto :done

set "dir=%~dp1"
set "name=%~nx1"

rem Если это файл — убираем последнее расширение
if exist "%~1\" (
  set "base=%name%"
) else (
  for %%F in ("%name%") do set "base=%%~nF"
)

set "out=%dir%[ЯД] %base%.txt"
type nul > "%out%"

shift
goto :loop

:done
exit /b 0
