@echo off
rem Open the sci-fi plate armor lab page (workspace\ultima-online\plate-armor-lab\index.html) in your browser, or say how to build it when it is missing.
call "%~dp0..\_shared\common.bat" || exit /b 1
if not exist "workspace\ultima-online\plate-armor-lab\index.html" (
  echo Build the sci-fi plate armor lab first with python games\ultima-online\outfit-lab\build_plate_armor.py
  exit /b 1
)
start "" "workspace\ultima-online\plate-armor-lab\index.html"
