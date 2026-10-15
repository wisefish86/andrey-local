@echo off
chcp 1251
:Loop
if "%~1"=="" goto End
"D:\System\Programs\NConvert\nconvert.exe" -wmopacity 15 -wmflag center -wmfile "D:\YandexDisk\Ресурсы\Автоматизация\Скрипты\Все скрипты\Для работы\_Конвертация в nconvert\!watermark.png" -out webp -q 75 
shift
goto Loop
:End
pause