@echo off
REM ===========================================================================
REM KaeKae run snapshot - freezes the evidence for one test run into
REM   runs\<timestamp>-<label>\
REM Usage:  snapshot.bat L3-dupes        (run from the project folder)
REM ===========================================================================
setlocal enabledelayedexpansion
if "%~1"=="" (
  echo Usage: snapshot.bat ^<label^>   e.g. snapshot.bat L3-dupes
  exit /b 1
)

set "LABEL=%~1"
set "STAMP="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"`) do set "STAMP=%%i"
if "%STAMP%"=="" set "STAMP=run"
set "DIR=runs\%STAMP%-%LABEL%"

if not exist runs mkdir runs 2>nul
if not exist "%DIR%" mkdir "%DIR%" 2>nul
if not exist "%DIR%\logs" mkdir "%DIR%\logs" 2>nul

echo [snapshot] collecting evidence into %DIR% ...

REM Telemetry event streams (skip the .lock sidecars, they are transient)
for %%F in (logs\*.jsonl logs\*.json) do (
  copy /y "%%F" "%DIR%\logs\" >nul 2>&1
)

REM Shared state stores + terminal liveness
for %%F in (bot_state.json talk_state.json dedupe_claims.json outbound_gate.json ^
            broadcast_queue.json config.json chat_outbox.jsonl ^
            command_inbox.jsonl terminal_heartbeats.json pagination.json) do (
  if exist "%%F" copy /y "%%F" "%DIR%\" >nul 2>&1
)

echo [snapshot] files captured:
dir /b "%DIR%" 2>nul
dir /b "%DIR%\logs" 2>nul
echo.
echo [snapshot] DONE -^> %CD%\%DIR%
echo [snapshot] Record this path in FAULTS.md for the test you just ran.
echo.
endlocal