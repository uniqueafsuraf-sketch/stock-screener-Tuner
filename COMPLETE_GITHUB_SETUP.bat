@echo off
setlocal
cd /d "%~dp0"
title StocksTunerStation - Finish GitHub + Render

set "GD=%LOCALAPPDATA%\GitHubDesktop"
set "GIT=%GD%\app-3.5.12\resources\app\git\cmd\git.exe"
set "GITHUB_CLI=%GD%\bin\github.bat"

if not exist "%GIT%" (
  for /d %%A in ("%GD%\app-*") do set "GIT=%%A\resources\app\git\cmd\git.exe"
)

if not exist "%GIT%" (
  set "GIT=%~dp0tools\MinGit\cmd\git.exe"
)

echo.
echo ============================================
echo   Finish setup (GitHub Desktop + Render)
echo ============================================
echo.
echo Your code is ready on branch: main
echo.

"%GIT%" remote get-url origin >nul 2>&1
if %errorlevel% equ 0 (
  echo GitHub remote already set. Pushing latest...
  "%GIT%" push -u origin main
  if errorlevel 1 (
    echo Push failed - sign in via GitHub Desktop, then run this file again.
    pause
    exit /b 1
  )
  goto :render
)

echo Opening this project in GitHub Desktop...
echo.
if exist "%GITHUB_CLI%" (
  call "%GITHUB_CLI%" open "%CD%"
) else if exist "%GD%\GitHubDesktop.exe" (
  start "" "%GD%\GitHubDesktop.exe"
) else (
  start "" "https://desktop.github.com"
)

echo.
echo -------- IN GITHUB DESKTOP (do once) --------
echo.
echo 1. Sign in if asked
echo 2. If it says "not a Git repository":
echo      click "create a repository" in this folder
echo 3. Click the blue button: "Publish repository"
echo 4. Name: stockstunerstation
echo 5. Uncheck "Keep private" (easier for Render free tier)
echo 6. Click Publish repository
echo.
echo When done, press any key here to push and open Render...
pause >nul

"%GIT%" remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo.
  echo [WAIT] No GitHub remote yet.
  echo Run Publish in GitHub Desktop, then double-click this file again.
  echo.
  pause
  exit /b 1
)

echo Pushing to GitHub...
"%GIT%" push -u origin main
if errorlevel 1 (
  echo Push failed. Use GitHub Desktop: Repository -^> Push origin
  pause
  exit /b 1
)

:render
echo.
echo -------- RENDER (permanent site) --------
echo.
echo 1. Dashboard opens in your browser
echo 2. Open service: stockstunerstation
echo 3. Manual Deploy -^> Deploy latest commit
echo 4. Wait until status is LIVE (green)
echo 5. Test: https://stockstunerstation.onrender.com/api/health
echo.
start https://dashboard.render.com
start notepad "%~dp0RENDER_FIX.md"
echo.
pause
