@echo off
REM Push ERCOT Battery Analyzer to GitHub
REM Prerequisites: Repository must already exist on GitHub at:
REM   https://github.com/Raj-Comet/modo-energy-task

echo ======================================================
echo ERCOT Battery Revenue Stack Analyzer
echo Push to GitHub Script
echo ======================================================
echo.
echo Username: Raj-Comet
echo Repository: modo-energy-task
echo.

setlocal enabledelayedexpansion

REM Check if already in git repository
cd /d "e:\ERCOT Battery Revenue Stack Analyzer\Modo Energy Task"

if not exist ".git" (
    echo ERROR: Not a git repository. Run from project root.
    pause
    exit /b 1
)

echo Checking GitHub repository...
echo.

REM Check if remote already exists
git remote get-url origin >nul 2>&1
if !errorlevel! equ 0 (
    echo Remote already configured:
    git remote -v
    echo.
) else (
    echo Adding remote origin...
    git remote add origin https://github.com/Raj-Comet/modo-energy-task.git
    if !errorlevel! neq 0 (
        echo ERROR: Failed to add remote
        pause
        exit /b 1
    )
    echo Remote added successfully.
    echo.
)

REM Ensure we're on main branch
git branch -M main

echo Pushing code to GitHub...
echo.
git push -u origin main

if !errorlevel! equ 0 (
    echo.
    echo ======================================================
    echo SUCCESS! Code pushed to GitHub
    echo ======================================================
    echo.
    echo Repository URL:
    echo https://github.com/Raj-Comet/modo-energy-task
    echo.
    echo View your repository in the browser? (Y/n)
    set /p answer=
    if /i "!answer!"=="y" (
        start https://github.com/Raj-Comet/modo-energy-task
    )
) else (
    echo.
    echo ======================================================
    echo ERROR: Push failed
    echo ======================================================
    echo.
    echo Make sure the repository exists on GitHub at:
    echo https://github.com/Raj-Comet/modo-energy-task
    echo.
    echo To create it:
    echo 1. Go to https://github.com/new
    echo 2. Name: "modo-energy-task"
    echo 3. Click "Create repository"
    echo 4. Run this script again
    echo.
)

pause
