@echo off
rem Run the Python test suite (Blender tests run when Blender is found, the UO test when SPRITEMOTION_UO_SOURCE is set).
rem args: [pytest arguments]  e.g. -k sample
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" -m pytest tests %*
