@echo off
setlocal
call "%~dp0apply_all.bat" %*
exit /b %errorlevel%
