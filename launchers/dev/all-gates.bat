@echo off
rem Run the three CLAUDE.md checks in order (pytest, outfit-lab unittest, agents check) and exit non-zero if any fails.
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
set "SM_FAIL=0"
"%SPRITEMOTION_PYTHON%" -m pytest -q || set "SM_FAIL=1"
pushd games\ultima-online\outfit-lab || exit /b 1
"%SPRITEMOTION_PYTHON%" -m unittest -q || set "SM_FAIL=1"
popd
"%SPRITEMOTION_PYTHON%" tools\agents\run.py --check || set "SM_FAIL=1"
if "%SM_FAIL%"=="0" (echo All gates passed.) else (echo A gate failed.)
exit /b %SM_FAIL%
