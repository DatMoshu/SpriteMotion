@echo off
rem Open the tracksuit lab page (workspace\ultima-online\tracksuit-lab\index.html) in your browser, or say how to build it when it is missing.
call "%~dp0..\_shared\common.bat" || exit /b 1
if not exist "workspace\ultima-online\tracksuit-lab\index.html" (
  echo Build with python games\ultima-online\outfit-lab\build_tracksuit.py first.
  exit /b 1
)
start "" "workspace\ultima-online\tracksuit-lab\index.html"
