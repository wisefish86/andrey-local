@echo off
chcp 65001 >nul
title Anytype to Notion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Import.ps1"
if errorlevel 1 (
  echo.
  echo Import failed. Press any key to close.
  pause >nul
)
