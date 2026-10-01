@echo off
REM ===========================================================================
REM  KaeKae rollback tool - three levels of "get me back to a working build"
REM
REM    rollback.bat 1 <file>   restore ONE file to the last commit
REM    rollback.bat 2          restore the whole pre-evaluation build
REM                            (11 files from _prefeval_backup\)
REM    rollback.bat 3          restore the ORIGINAL pre-change codebase
REM                            (git bc1d29f - complete, unlike the 6-file
REM                             _presync_backup\ folder)
REM    rollback.bat verify     dry-run: parses every restore target WITHOUT
REM                            touching your working tree
REM    rollback.bat list       show what each level would restore
REM
REM  Add --yes to skip the confirmation prompt on levels 2 and 3.
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "LEVEL=%~1"
set "TARGET=%~2"
set "ASSUME=%~3"
set "ORIGIN=bc1d29f"

if "%LEVEL%"=="" goto :usage
if /i "%LEVEL%"=="1" goto :level1
if /i "%LEVEL%"=="2" goto :level2
if /i "%LEVEL%"=="3" goto :level3
if /i "%LEVEL%"=="verify" goto :verify
if /i "%LEVEL%"=="list" goto :list
goto :usage

REM ---------------------------------------------------------------- LEVEL 1
:level1
if "%TARGET%"=="" (
  echo [rollback] Level 1 needs a filename:  rollback.bat 1 kaekae_bot.py
  exit /b 1
)
echo [rollback] LEVEL 1 - restoring "%TARGET%" from the last commit...
git checkout -- "%TARGET%"
if errorlevel 1 (
  echo [rollback] FAILED - file not tracked or not found: %TARGET%
  exit /b 1
)
echo [rollback] done. Verify with:  python -m py_compile "%TARGET%"
exit /b 0

REM ---------------------------------------------------------------- LEVEL 2
:level2
if not exist "_prefeval_backup" (
  echo [rollback] ERROR: _prefeval_backup\ is missing!
  echo           Use level 3 instead:  rollback.bat 3
  exit /b 1
)
if /i not "%ASSUME%"=="--yes" (
  echo.
  echo [rollback] LEVEL 2 overwrites 11 files with the pre-evaluation build.
  echo           This does NOT undo the Phase 1-7 rework - it returns the
  echo           exact build frozen before live testing.
  echo.
  set /p OK="           Type YES to continue: "
  if /i not "!OK!"=="YES" (
    echo [rollback] cancelled.
    exit /b 0
  )
)
echo [rollback] LEVEL 2 - restoring pre-evaluation build...
for %%F in (_prefeval_backup\*.py _prefeval_backup\*.json) do (
  copy /y "%%F" "%CD%\%%~nxF" >nul
  echo    restored %%~nxF
)
echo [rollback] done. Verify:  python -m py_compile kaekae_bot.py cef_probe.py
exit /b 0

REM ---------------------------------------------------------------- LEVEL 3
:level3
if /i not "%ASSUME%"=="--yes" (
  echo.
  echo [rollback] LEVEL 3 returns the WHOLE codebase to the original
  echo           pre-change state (git commit %ORIGIN%).
  echo           ALL Phase 1-7 work is undone.
  echo.
  set /p OK="           Type YES to continue: "
  if /i not "!OK!"=="YES" (
    echo [rollback] cancelled.
    exit /b 0
  )
)
echo [rollback] LEVEL 3 - restoring the original codebase from %ORIGIN%...
git checkout %ORIGIN% -- *.py *.json *.bat *.txt
if errorlevel 1 (
  echo [rollback] git checkout failed. Is %ORIGIN% present?  git log --oneline
  exit /b 1
)
if not exist "rolled_back_tooling" mkdir "rolled_back_tooling" 2>nul
for %%F in (_test_core.py CHANGES.md FAULTS.md TEST_RUNBOOK.md snapshot.bat rollback.bat .gitignore) do (
  if exist "%%F" move /y "%%F" "rolled_back_tooling\" >nul 2>&1
)
echo    code + data restored to the original state
echo    new tooling moved to rolled_back_tooling\ (not deleted)
echo [rollback] done. Git history is untouched - commits 833e908 / c027f64
echo           still hold the full rework if you want it back.
exit /b 0

REM ---------------------------------------------------------------- VERIFY
:verify
echo [rollback] DRY RUN - parsing every restore target, changing nothing...
python rollback_verify.py
if errorlevel 1 (
  echo [rollback] VERIFY FAILED - a restore target does not parse.
  exit /b 1
)
echo [rollback] VERIFY PASSED - every restore target is syntactically valid.
echo            Level 1 (git HEAD), Level 2 (_prefeval_backup) and
echo            Level 3 (git bc1d29f) are all usable.
exit /b 0

REM ------------------------------------------------------------------- LIST
:list
echo.
echo  LEVEL 1  git checkout -- ^<file^>
echo           One file back to HEAD. Instant, safe.
echo.
echo  LEVEL 2  _prefeval_backup\  (%CD%\_prefeval_backup)
for %%F in (_prefeval_backup\*) do echo             %%~nxF
echo           The exact build frozen before live testing.
echo.
echo  LEVEL 3  git %ORIGIN%   (the complete original codebase)
echo           Pre-rework state. Use git, NOT _presync_backup\ - that folder
echo           holds only 6 files and would leave cef_explorer.py,
echo           chat_worker.py and calibrate_camfrog.py from the new build,
echo           producing a broken mix.
echo.
git --no-pager log --oneline -4
echo.
exit /b 0

REM ------------------------------------------------------------------ USAGE
:usage
echo Usage:
echo   rollback.bat 1 ^<file^>      restore one file from the last commit
echo   rollback.bat 2             restore the pre-evaluation build
echo   rollback.bat 3             restore the ORIGINAL codebase (git bc1d29f)
echo   rollback.bat verify        dry-run: validate every restore target
echo   rollback.bat list          show what each level restores
echo.
echo Add --yes to levels 2 and 3 to skip the confirmation prompt.
exit /b 1