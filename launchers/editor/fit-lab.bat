@echo off
rem Start Fit Lab (asset-pack slot fitting and body hiding) for a pack on http://127.0.0.1:8774 and keep it running here until Ctrl+C.
rem args: <pack>  (or set SPRITEMOTION_FIT_PACK)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
set "SM_PACK=%~1"
if not defined SM_PACK set "SM_PACK=%SPRITEMOTION_FIT_PACK%"
if not defined SM_PACK (
  echo Usage: fit-lab.bat ^<pack^>   ^(or set SPRITEMOTION_FIT_PACK^)
  exit /b 1
)
if not exist "workspace\ultima-online\fit-lab\%SM_PACK%\manifest.json" (
  echo No export for %SM_PACK%. See tools\fit-lab\README.md
  exit /b 1
)
"%SPRITEMOTION_PYTHON%" tools\fit-lab\run.py serve --pack "%SM_PACK%"
