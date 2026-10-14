@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ADMIN ELEVATION] Requesting Windows Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

title KaeKae_Toad ^& PepeFrog Live Room Monitor Terminal
echo ===============================================================================
echo   KAEKAE_TOAD ^& PEPEFROG LIVE ROOM MONITOR + TRIGGER PIPELINE
echo ===============================================================================
python setup_env.py
python room_monitor.py
pause
