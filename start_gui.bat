@echo off
title KaeKae_Toad ^& PepeFrog Bot GUI Launcher
color 0A
cd /d "%~dp0"

echo =====================================================================
echo           KAEKAE_TOAD ^& PEPEFROG AUTOMATION BOT - GUI LAUNCHER
echo =====================================================================
echo.

:: 1. Check for Node.js
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    color 0C
    echo [ERROR] Node.js is not installed or not in your system PATH!
    echo Please download and install Node.js (LTS version) from:
    echo     https://nodejs.org/
    echo.
    echo After installing Node.js, run this file again.
    echo.
    pause
    exit /b 1
)

echo [OK] Node.js detected:
node -v
echo.

:: 2. Check if node_modules exists, otherwise install dependencies
if not exist "node_modules\" (
    echo [INFO] First time setup: Installing bot dependencies...
    echo Running 'npm install' (this may take 1-2 minutes)...
    echo.
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        color 0C
        echo.
        echo [ERROR] Failed to install dependencies. Please check your internet connection.
        pause
        exit /b 1
    )
    echo.
    echo [OK] Dependencies installed successfully!
    echo.
)

:: 3. Launch the browser after a short delay
echo [INFO] Starting the Bot Web GUI server...
echo [INFO] Opening interface at http://localhost:3000
echo.

start "" "http://localhost:3000"

:: 4. Start the Vite server
call npm run dev

pause
