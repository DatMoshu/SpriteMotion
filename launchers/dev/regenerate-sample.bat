@echo off
rem Regenerate examples\sample-character (deterministic; the tests check it matches what is committed).
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" examples\sample-character\make_sample.py
