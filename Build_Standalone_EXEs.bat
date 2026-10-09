@echo off
title Build Standalone Camfrog .EXE Files
cd /d "C:\Users\newbe\AIBot"
echo Installing PyInstaller and compiling standalone .exe executables...
python -m pip install --upgrade pyinstaller pywinauto pyttsx3
python -m PyInstaller --noconfirm --onefile --console --name CamfrogRoomMonitor room_monitor.py
python -m PyInstaller --noconfirm --onefile --console --name CamfrogBot camfrog_bot.py
copy /Y dist\CamfrogRoomMonitor.exe "C:\Users\newbe\AIBot\CamfrogRoomMonitor.exe"
copy /Y dist\CamfrogBot.exe "C:\Users\newbe\AIBot\CamfrogBot.exe"
echo.
echo Built CamfrogRoomMonitor.exe and CamfrogBot.exe in C:\Users\newbe\AIBot!
pause
