@echo off
rem Local only. For public internet URL run SITE_LIVE_NOW.bat or OPEN_MY_LIVE_SITE.bat

setlocal

cd /d "%~dp0"

title StocksTunerStation



if not exist ".venv\Scripts\python.exe" (

  echo First run - installing dependencies...

  call "%~dp0install.bat"

  if errorlevel 1 exit /b 1

)



call "%~dp0start_dashboard.bat"

