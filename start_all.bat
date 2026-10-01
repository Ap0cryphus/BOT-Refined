@echo off
title KaeKae Bot Cluster Launcher
cd /d "%~dp0"
echo ========================================================
echo   Launching KaeKae Bot 3-Terminal Cluster
echo ========================================================
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" launch_kaekae.py
) else (
    python launch_kaekae.py
)
pause
