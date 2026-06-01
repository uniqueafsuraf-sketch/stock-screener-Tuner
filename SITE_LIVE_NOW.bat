@echo off
setlocal
cd /d "%~dp0"
title StocksTunerStation - Going live now

echo.
echo Starting your public site (works without Render)...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_public_site.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] Could not start. See data\server.log and data\tunnel.log
  pause
  exit /b 1
)

set /p URL=<data\public_url.txt
echo.
echo ============================================
echo   YOUR SITE IS LIVE
echo ============================================
echo.
echo   %URL%
echo.
echo Saved to: data\public_url.txt
echo Keep this PC on and do not close background processes.
echo.
start "" "%URL%"
echo Opening in browser...
pause
