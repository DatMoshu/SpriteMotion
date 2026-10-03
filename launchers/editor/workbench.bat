@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\workbench\run.py %*
