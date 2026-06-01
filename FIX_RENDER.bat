@echo off
setlocal
cd /d "%~dp0"
title Fix Render - empty repository error

echo.
echo ============================================
echo   Fix Render "repository is empty"
echo ============================================
echo.
echo Your CODE is here (not empty):
echo   https://github.com/uniqueafsuraf-sketch/stock-screener-Tuner
echo.
echo Render must use THAT repo, branch: main
echo.
echo -------- DO THIS IN RENDER --------
echo.
echo 1. Settings -^> Build ^& Deploy -^> Repository
echo 2. Connect: uniqueafsuraf-sketch / stock-screener-Tuner
echo 3. Branch: main
echo 4. Root Directory: (empty)
echo 5. Save, then Manual Deploy
echo.
start https://github.com/uniqueafsuraf-sketch/stock-screener-Tuner
start https://dashboard.render.com
start notepad "%~dp0FIX_RENDER_EMPTY_REPO.md"
pause
