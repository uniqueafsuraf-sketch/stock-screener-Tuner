@echo off
setlocal
cd /d "%~dp0"
title Deploy StocksTunerStation (permanent free site)

echo.
echo ============================================
echo   Permanent free website on Render.com
echo ============================================
echo.

set "ZIP=%~dp0stockstunerstation-deploy.zip"
echo Creating upload package...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CREATE_DEPLOY_ZIP.ps1"

if not exist "%ZIP%" (
  echo [ERROR] Could not create zip.
  pause
  exit /b 1
)

echo.
echo Created: %ZIP%
echo.
echo -------- FOLLOW THESE 4 STEPS --------
echo.
echo STEP 1 - GitHub (upload code, no Git install needed)
echo   Create repo name: stockstunerstation
echo   Upload files from the ZIP (or drag folder contents)
echo.
start https://github.com/new
timeout /t 2 /nobreak >nul

echo STEP 2 - Render (free hosting) - sign in with GitHub
start https://dashboard.render.com/select-repo?type=web
timeout /t 2 /nobreak >nul

echo STEP 3 - Render settings (copy/paste):
echo   Build: pip install -r requirements.txt
echo   Start: gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180
echo   Plan: Free
echo.
start notepad "%~dp0GO_LIVE_FREE.md"

echo ZIP ready:
explorer /select,"%ZIP%"
pause
