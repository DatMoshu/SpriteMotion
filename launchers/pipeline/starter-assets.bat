@echo off
rem Build the bundled CC0 starter equipment (or export it to Fit Lab with --prepare-lab) and print what it produced.
rem args: [item] [--list] [--prepare-lab] [--smoke]
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\starter-assets\run.py %*
