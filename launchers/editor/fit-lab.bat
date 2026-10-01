@echo off
@rem Fit lab: asset-pack slot fitting and body hiding. Pack: first argument, else SPRITEMOTION_FIT_PACK.
call "%~dp0..\_shared\common.bat" || exit /b 1
set "SM_PACK=%~1"
if not defined SM_PACK set "SM_PACK=%SPRITEMOTION_FIT_PACK%"
if not defined SM_PACK (
  echo Usage: fit-lab.bat ^<pack^>   ^(or set SPRITEMOTION_FIT_PACK^)
  pause
  exit /b 1
)
if not exist "workspace\ultima-online\fit-lab\%SM_PACK%\manifest.json" (
  echo No export for %SM_PACK%. See tools\fit-lab\README.md
  pause
  exit /b 1
)
"%SPRITEMOTION_PYTHON%" tools\fit-lab\run.py serve --pack %SM_PACK%
