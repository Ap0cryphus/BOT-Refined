@echo off
REM ==============================================================================
REM push_to_github.bat — Push Complete Bot-Refined Suite to GitHub master Branch
REM ==============================================================================

set REPO_URL=https://github.com/Ap0cryphus/BOT-Refined.git
set BRANCH=master

echo ====================================================================
echo   KaeKae_Toad ^& PepeFrog Suite: Push to GitHub (%BRANCH% branch)
echo   Target: %REPO_URL%
echo ====================================================================
echo.

git init
git checkout -b %BRANCH% 2>nul || git checkout %BRANCH%
git remote remove origin 2>nul
git remote add origin %REPO_URL%

git add .
git commit -m "Restore complete KaeKae_Toad & PepeFrog application suite" 2>nul

echo.
echo Choose authentication method:
echo 1) Push using Git Credential Manager
echo 2) Push using a GitHub Personal Access Token (PAT)
echo.
set /p AUTH_CHOICE="Enter choice [1 or 2]: "

if "%AUTH_CHOICE%"=="2" (
    set /p GH_USER="Enter your GitHub username [Ap0cryphus]: "
    if "%GH_USER%"=="" set GH_USER=Ap0cryphus
    set /p GH_TOKEN="Enter your GitHub Personal Access Token (PAT): "
    echo Pushing changes to %BRANCH% branch...
    git push -u https://%GH_USER%:%GH_TOKEN%@github.com/Ap0cryphus/BOT-Refined.git %BRANCH% --force
) else (
    echo Pushing changes to %BRANCH% branch...
    git push -u origin %BRANCH% --force
)

echo.
echo Operation completed!
pause
