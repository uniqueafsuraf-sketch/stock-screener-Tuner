@echo off
setlocal
cd /d "%~dp0"
title StocksTunerStation

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment missing. Run install.bat or START.bat first.
  pause
  exit /b 1
)

echo.
echo Stopping old servers on ports 5050, 8765...
for %%p in (5050 8765 5051) do (
  for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr :%%p ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
  )
)
timeout /t 2 /nobreak >nul

echo.
echo ============================================
echo   StocksTunerStation is starting...
echo ============================================
echo   Browser will open automatically.
echo   Keep this window OPEN while you use the site.
echo ============================================
echo.

.venv\Scripts\python.exe start_dashboard.py

echo.
echo Server stopped.
pause
