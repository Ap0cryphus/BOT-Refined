@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ADMIN ELEVATION] Requesting Windows Administrator privileges so KaeKae_Toad can type ^& click inside Camfrog...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

title KaeKae_Toad Camfrog Bot (Silent Auto-Listener ^& All 20 Triggers)
echo ===============================================================================
echo   KAEKAE_TOAD CAMFROG BOT — SILENT AUTO-LISTENER ^& ALL 20 TRIGGERS
echo ===============================================================================
python setup_env.py
python camfrog_bot.py
pause
