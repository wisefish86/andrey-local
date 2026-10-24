@echo off
chcp 65001 >nul
call "%~dp0Миграция плюсов\Миграция плюсов - ПРОВЕРКА.bat"
exit /b %ERRORLEVEL%
