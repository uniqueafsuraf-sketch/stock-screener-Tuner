@echo off
setlocal
cd /d "%~dp0"
title Publish StocksTunerStation to GitHub

set "GIT=%~dp0tools\MinGit\cmd\git.exe"
if not exist "%GIT%" (
  echo Git not found. Run this folder setup from Cursor first, or install GitHub Desktop.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   Publish to GitHub (2 minutes)
echo ============================================
echo.

"%GIT%" status >nul 2>&1
if errorlevel 1 (
  echo Initializing git...
  "%GIT%" init
  "%GIT%" branch -M main
)

echo Your code is committed locally on branch: main
echo.
echo -------- DO THIS IN GITHUB DESKTOP --------
echo.
echo 1. Open GitHub Desktop (Start menu)
echo 2. File -^> Add local repository
echo 3. Choose this folder:
echo    %CD%
echo 4. If asked, click "create a repository" here
echo 5. Click "Publish repository"
echo    Name: stockstunerstation
echo    UNCHECK "Keep this code private" if you want free Render
echo 6. Click Publish repository
echo.
start "" "https://github.com/apps/desktop"
timeout /t 2 /nobreak >nul
start "" "%CD%"

echo.
echo -------- AFTER PUBLISH: FIX RENDER --------
echo.
echo 7. Open Render dashboard
start https://dashboard.render.com
echo 8. Open RENDER_FIX.md for deploy settings
start notepad "%~dp0RENDER_FIX.md"
echo.
pause
