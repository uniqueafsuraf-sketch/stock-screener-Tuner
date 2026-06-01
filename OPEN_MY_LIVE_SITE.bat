@echo off
setlocal
cd /d "%~dp0"
if not exist "data\public_url.txt" (
  echo No live URL yet. Run SITE_LIVE_NOW.bat first.
  pause
  exit /b 1
)
set /p URL=<data\public_url.txt
start "" "%URL%"
echo %URL%
