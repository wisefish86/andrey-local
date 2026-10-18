@echo off
setlocal
call "%~dp0check_only.bat" %*
exit /b %errorlevel%
