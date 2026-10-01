@echo off
title KaeKae Camfrog AI Bot
cd /d "%~dp0"

echo ======================================================
echo           Starting KaeKae Camfrog AI Bot
echo ======================================================

:: Clean old audio chunks so no stale backlogs are transcribed
if exist "audio_clips\*.wav" (
    echo [CLEANUP] Clearing old audio queue...
    del /q "audio_clips\*.wav" >nul 2>&1
)

:: Run directly with virtual environment python
if exist "venv\Scripts\python.exe" (
    echo [ENV] Virtual environment active. Starting KaeKae...
    "venv\Scripts\python.exe" kaekae_bot.py
) else (
    echo [ENV] Using system python...
    python kaekae_bot.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] KaeKae Bot stopped with an error.
    pause
)