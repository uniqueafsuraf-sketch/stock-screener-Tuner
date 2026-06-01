@echo off
setlocal
cd /d "%~dp0"
title Deploy to Render (one click)

echo.
echo This opens Render's deploy page for YOUR GitHub repo.
echo Sign in, click Apply / Create Web Service, wait for Live.
echo.
echo Repo: uniqueafsuraf-sketch / stock-screener-Tuner
echo Branch: main
echo.

start "" "https://render.com/deploy?repo=https://github.com/uniqueafsuraf-sketch/stock-screener-Tuner"

echo.
echo After deploy finishes, your URL may be:
echo   https://stockstunerstation.onrender.com
echo   OR a new name Render assigns - check the Render dashboard.
echo.
pause
