@echo off
cd /d "%~dp0"
echo Stopping StocksTunerStation...
for %%p in (5050 8765 5051 8080) do (
  for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr :%%p ^| findstr LISTENING') do (
    echo Stopping PID %%a on port %%p
    taskkill /F /PID %%a >nul 2>&1
  )
)
timeout /t 2 /nobreak >nul
echo Done. Run START.bat to open again.
pause
