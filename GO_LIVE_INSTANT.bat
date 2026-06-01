@echo off
setlocal
cd /d "%~dp0"
title StocksTunerStation - Live on the internet (free)

echo.
echo ============================================
echo   StocksTunerStation - FREE public URL
echo ============================================
echo.
echo This gives you a free link like:
echo   https://something.trycloudflare.com
echo.
echo Keep BOTH windows open while you share the link.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Installing app first...
  call "%~dp0install.bat"
  if errorlevel 1 exit /b 1
)

if not exist "tools\cloudflared.exe" (
  echo Downloading tunnel tool (one-time, ~20MB)...
  if not exist "tools" mkdir tools
  powershell -NoProfile -Command ^
    "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'tools\cloudflared.exe'"
  if not exist "tools\cloudflared.exe" (
    echo [ERROR] Could not download cloudflared. Check internet and run again.
    pause
    exit /b 1
  )
)

echo Stopping old servers...
call "%~dp0stop_dashboard.bat" >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo [1/2] Starting StocksTunerStation...
start "StocksTunerStation Server" cmd /k "cd /d "%~dp0" && .venv\Scripts\python.exe start_dashboard.py --no-browser"

echo Waiting for server...
timeout /t 8 /nobreak >nul

echo.
echo [2/2] Opening public tunnel...
echo.
echo >>> COPY THE https://....trycloudflare.com URL FROM THE WINDOW BELOW <<<
echo.
start "Your Public URL" cmd /k "cd /d "%~dp0\tools" && cloudflared.exe tunnel --url http://127.0.0.1:5050"

echo.
echo Done. Two windows are running:
echo   - StocksTunerStation Server
echo   - Your Public URL  ^(share the https link^)
echo.
echo For a permanent site (stockstunerstation.onrender.com), run DEPLOY_NOW.bat
echo.
pause
