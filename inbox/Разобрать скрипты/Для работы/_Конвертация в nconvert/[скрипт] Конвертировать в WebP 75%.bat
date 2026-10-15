@echo off
chcp 1251
:Loop
if "%~1"=="" goto End
"D:\System\Programs\NConvert\nconvert.exe" -out webp -q 75 "%~1"
shift
goto Loop
:End
pause