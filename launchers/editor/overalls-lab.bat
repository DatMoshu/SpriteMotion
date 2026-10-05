@echo off
@rem Opens the offline overalls outfit preview built by games\ultima-online\outfit-lab\build_overalls.py.
call "%~dp0..\_shared\common.bat" || exit /b 1
if not exist "workspace\ultima-online\overalls-lab\index.html" (
  echo Build with python games\ultima-online\outfit-lab\build_overalls.py first.
  pause
  exit /b 1
)
start "" "workspace\ultima-online\overalls-lab\index.html"
