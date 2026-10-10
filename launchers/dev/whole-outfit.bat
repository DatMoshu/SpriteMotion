@echo off
rem Build a whole outfit from a Fit Lab catalogue and composite contact sheets in client layer order (local output, prints a per-slot table).
rem args: build|body|composite ... (see tools\whole-outfit\run.py --help)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\whole-outfit\run.py %*
