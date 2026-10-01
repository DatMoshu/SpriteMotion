@rem Python test suite. Blender tests run when Blender is found; the UO test runs when SPRITEMOTION_UO_SOURCE is set.
@rem Extra arguments go to pytest, e.g.  run-tests.bat -k sample
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" -m pytest tests %*
