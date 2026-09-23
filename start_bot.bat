@echo off
cd /d "C:\Users\newbe\OneDrive\Documents\Projects\AIBot"

if not exist ".venv\Scripts\python.exe" (
	echo Creating Python environment...
	py -m venv .venv
	if errorlevel 1 (
		echo Failed to create the Python environment.
		pause
		exit /b 1
	)
)

echo Installing or updating dependencies...
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
	echo Failed to install dependencies.
	pause
	exit /b 1
)

".venv\Scripts\python.exe" bot.py
pause