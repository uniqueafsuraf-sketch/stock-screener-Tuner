@echo off
cd /d "%~dp0"
title StocksTunerStation (production)
echo.
echo Production mode — listening on all interfaces (port 5050)
echo Set STS_PUBLIC_URL to your domain, e.g. https://stockstunerstation.com
echo.
set STS_HOST=0.0.0.0
set STS_PORT=5050
if not defined STS_PUBLIC_URL set STS_PUBLIC_URL=https://stockstunerstation.com
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe start_dashboard.py --no-browser
) else (
  python start_dashboard.py --no-browser
)
pause
