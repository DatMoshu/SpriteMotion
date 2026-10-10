@echo off
rem Start Content Studio and Fit Lab together for a pack, open both in your browser, and keep them running here until Ctrl+C.
rem args: [pack]  (default: SPRITEMOTION_FIT_PACK, else the bundled cc0-starter)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\workbench\run.py %*
