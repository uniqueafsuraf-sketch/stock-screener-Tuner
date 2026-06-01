@echo off
setlocal
cd /d "%~dp0"
title StocksTunerStation - Install

echo.
echo ============================================
echo   StocksTunerStation - First-time setup
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not installed or not on PATH.
  echo.
  echo 1. Go to https://www.python.org/downloads/
  echo 2. Download Python 3.11 or newer
  echo 3. During install, CHECK "Add python.exe to PATH"
  echo 4. Run this file again.
  echo.
  pause
  exit /b 1
)

python --version
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create .venv
    pause
    exit /b 1
  )
)

echo Installing packages (may take 1-2 minutes)...
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\pip.exe install -r requirements.txt -q
if errorlevel 1 (
  echo [ERROR] pip install failed. Check your internet connection.
  pause
  exit /b 1
)

echo.
echo [OK] Setup complete. You can now run START.bat
echo.
pause
exit /b 0
