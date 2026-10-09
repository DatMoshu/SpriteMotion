@echo off
rem Open the outfit lab page (workspace\ultima-online\outfit-lab\index.html) in your browser, or say how to build it when it is missing.
call "%~dp0..\_shared\common.bat" || exit /b 1
if not exist "workspace\ultima-online\outfit-lab\index.html" (
  echo Build the outfit lab first. See games\ultima-online\outfit-lab\README.md
  exit /b 1
)
start "" "workspace\ultima-online\outfit-lab\index.html"
