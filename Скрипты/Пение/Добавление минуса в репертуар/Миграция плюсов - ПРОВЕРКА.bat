@echo off
chcp 65001 >nul
call "%~dp0Инструменты репертуара\Миграция плюсов\Миграция плюсов - ПРОВЕРКА.bat"
exit /b %ERRORLEVEL%
