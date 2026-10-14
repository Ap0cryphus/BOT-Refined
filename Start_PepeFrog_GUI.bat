@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ADMIN ELEVATION] Requesting Windows Administrator privileges so KaeKae_Toad ^& PepeFrog can click ^& type inside Camfrog...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

title KaeKae_Toad ^& PepeFrog Command Center (ADMIN MODE)
echo ===============================================================================
echo   KaeKae_Toad ^& PepeFrog Command Center — Purging Old Cache ^& Starting GUI
echo ===============================================================================
if exist "__pycache__" rd /s /q "__pycache__"
python setup_env.py
python main.py --gui --auto-start
pause
