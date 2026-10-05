@echo off
@rem Opens the offline sci-fi plate armor preview built by games\ultima-online\outfit-lab\build_plate_armor.py.
call "%~dp0..\_shared\common.bat" || exit /b 1
if not exist "workspace\ultima-online\plate-armor-lab\index.html" (
  echo Build with python games\ultima-online\outfit-lab\build_plate_armor.py first.
  pause
  exit /b 1
)
start "" "workspace\ultima-online\plate-armor-lab\index.html"
