@echo off

setlocal

cd /d "%~dp0"

title Publish StocksTunerStation to GitHub



set "GD=%LOCALAPPDATA%\GitHubDesktop"
set "GIT=%GD%\app-3.5.12\resources\app\git\cmd\git.exe"
set "GITHUB_CLI=%GD%\bin\github.bat"

if not exist "%GIT%" (
  for /d %%A in ("%GD%\app-*") do set "GIT=%%A\resources\app\git\cmd\git.exe"
)
if not exist "%GIT%" set "GIT=%~dp0tools\MinGit\cmd\git.exe"

if not exist "%GIT%" (
  echo Git not found. Install GitHub Desktop from https://desktop.github.com
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

echo Opening GitHub Desktop with this folder...

if exist "%GITHUB_CLI%" (
  call "%GITHUB_CLI%" open "%CD%"
) else (
  start "" "%GD%\GitHubDesktop.exe"
)

echo.

echo 1. Sign in if needed

echo 2. If asked, click "create a repository" here

echo 3. Click "Publish repository"

echo    Name: stockstunerstation

echo    UNCHECK "Keep this code private" if you want free Render

echo 6. Click Publish repository

echo.

echo.

echo After publish, run: COMPLETE_GITHUB_SETUP.bat



echo.

echo -------- AFTER PUBLISH: FIX RENDER --------

echo.

echo 7. Open Render dashboard

start https://dashboard.render.com

echo 8. Open RENDER_FIX.md for deploy settings

start notepad "%~dp0RENDER_FIX.md"

echo.

pause

