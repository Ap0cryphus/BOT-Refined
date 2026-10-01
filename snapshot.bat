@echo off
REM ===========================================================================
REM KaeKae run snapshot - freezes the evidence for one test run into
REM   runs\<timestamp>-<label>\
REM Usage:  snapshot.bat L3-dupes        (run from the project folder)
REM ===========================================================================
setlocal
if "%~1"=="" (
  echo Usage: snapshot.bat <label>   e.g. snapshot.bat L3-dupes
  exit /b 1
)

set "LABEL=%~1"
set "STAMP=%DATE:~-4%%TIME::=0%"
set "STAMP=%STAMP: =0%"
set "STAMP=%STAMP:,=%"
set "DIR=runs\%STAMP%-%LABEL%"

if not exist runs mkdir runs
mkdir "%DIR%"

echo [snapshot] collecting evidence into %DIR% ...

REM Telemetry logs (the JSONL event streams)
if exist logs mkdir "%DIR%\logs"
for %%F in (logs\*.jsonl) do copy "%%F" "%DIR%\logs\" >nul 2>&1
for %%F in (logs\*.json) do copy "%%F" "%DIR%\logs\" >nul 2>&1

REM Shared state stores
for %%F in (bot_state.json talk_state.json dedupe_claims.json outbound_gate.json broadcast_queue.json config.json chat_outbox.jsonl command_inbox.jsonl) do (
  if exist "%%F" copy "%%F" "%DIR%\" >nul 2>&1
)

REM Terminal liveness
for %%F in (terminal_heartbeats.json) do (
  if exist "%%F" copy "%%F" "%DIR%\" >nul 2>&1
)

echo.
echo [snapshot] DONE -> %CD%\%DIR%
echo [snapshot] Record this path in FAULTS.md for the test you just ran.
echo.
endlocal