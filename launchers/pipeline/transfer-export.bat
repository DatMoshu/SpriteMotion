@echo off
rem Export a finished uo-content build job as a transfer artifact (transfer.json plus cropped frames) and read it back to check it.
rem args: --job <job dir> --out <new empty dir>
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\transfer-export\run.py %*
