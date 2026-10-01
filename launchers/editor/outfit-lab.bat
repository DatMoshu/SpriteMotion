@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist "workspace\ultima-online\outfit-lab\index.html" (
  echo Build the outfit lab first. See games\ultima-online\outfit-lab\README.md
  pause
  exit /b 1
)
start "" "workspace\ultima-online\outfit-lab\index.html"
