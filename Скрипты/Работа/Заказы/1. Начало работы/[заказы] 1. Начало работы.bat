@echo off
setlocal
chcp 65001 >nul
title Начало работы с заказом
if "%~1"=="" (
  echo Перетащи папку заказа, архив или файлы на этот BAT или его ярлык.
  echo.
  pause
  exit /b 1
)
set "PYTHON="
where py.exe >nul 2>nul
if not errorlevel 1 set "PYTHON=py.exe"
if not defined PYTHON (
  where python.exe >nul 2>nul
  if not errorlevel 1 set "PYTHON=python.exe"
)
if not defined PYTHON (
  echo Python не найден. Установи Python или добавь его в PATH.
  pause
  exit /b 1
)
"%PYTHON%" -c "import openpyxl, pyperclip" >nul 2>nul
if errorlevel 1 (
  echo Не найдены библиотеки openpyxl и/или pyperclip.
  echo Выполни: %PYTHON% -m pip install openpyxl pyperclip
  pause
  exit /b 1
)
"%PYTHON%" "%~dp0rename.py" %*
set "CODE=%errorlevel%"
if not "%CODE%"=="0" (
  echo.
  echo Ошибка выполнения (код %CODE%). Проверь rename.log рядом с rename.py.
  pause
)
exit /b %CODE%
