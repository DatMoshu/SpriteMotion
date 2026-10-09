@echo off
rem Run the outfit-lab unittest suite (games\ultima-online\outfit-lab) and print the result.
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
pushd games\ultima-online\outfit-lab || exit /b 1
"%SPRITEMOTION_PYTHON%" -m unittest -q
set "SM_RC=%errorlevel%"
popd
exit /b %SM_RC%
