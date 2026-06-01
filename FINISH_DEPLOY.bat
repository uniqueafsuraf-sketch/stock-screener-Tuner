@echo off
setlocal
cd /d "%~dp0"
title StocksTunerStation - Finish deploy (last step)

set "GD=%LOCALAPPDATA%\GitHubDesktop"
set "GIT=%GD%\app-3.5.12\resources\app\git\cmd\git.exe"
if not exist "%GIT%" for /d %%A in ("%GD%\app-*") do set "GIT=%%A\resources\app\git\cmd\git.exe"

echo.
echo ============================================
echo   Final step: point Render at your GitHub repo
echo ============================================
echo.
echo Code is on GitHub (pushed):
echo   uniqueafsuraf-sketch / stock-screener-Tuner  branch main
echo.
echo Render opens in your browser. YOU click once:
echo   1. Pick repo: stock-screener-Tuner
echo   2. Branch: main
echo   3. Deploy
echo.
echo This window will watch until the site is live...
echo.

start https://github.com/uniqueafsuraf-sketch/stock-screener-Tuner
start https://dashboard.render.com/select-repo?type=web

if exist "%GD%\bin\github.bat" call "%GD%\bin\github.bat" open "%CD%"

:waitloop
timeout /t 15 /nobreak >nul
curl.exe -s -o nul -w "%%{http_code}" https://stockstunerstation.onrender.com/api/health 2>nul | findstr /C:"200" >nul
if %errorlevel% equ 0 (
  echo.
  echo *** SITE IS LIVE ***
  start https://stockstunerstation.onrender.com
  start https://stockstunerstation.onrender.com/api/health
  echo.
  pause
  exit /b 0
)
echo Still waiting for Render deploy... fix repo in dashboard if needed.
goto waitloop
