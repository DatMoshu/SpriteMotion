@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist "workspace\ultima-online\tracksuit-lab\index.html" (
  echo Build with python games\ultima-online\outfit-lab\build_tracksuit.py first.
  pause
  exit /b 1
)
start "" "workspace\ultima-online\tracksuit-lab\index.html"
