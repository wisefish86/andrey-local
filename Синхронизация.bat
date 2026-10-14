@echo off
chcp 65001 >nul
title Andrey Local - Sync
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Синхронизация.ps1"
echo.
echo Press any key to close...
pause >nul
