@echo off
chcp 65001 >nul
call "%~dp0Инструменты репертуара\Миграция плюсов\Миграция плюсов - ПРИМЕНИТЬ.bat"
exit /b %ERRORLEVEL%
