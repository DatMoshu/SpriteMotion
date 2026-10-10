@echo off
rem Open the overalls lab page (workspace\ultima-online\overalls-lab\index.html) in your browser, or say how to build it when it is missing.
call "%~dp0..\_shared\common.bat" || exit /b 1
if not exist "workspace\ultima-online\overalls-lab\index.html" (
  echo Build the overalls lab first with python games\ultima-online\outfit-lab\build_overalls.py
  exit /b 1
)
start "" "workspace\ultima-online\overalls-lab\index.html"
