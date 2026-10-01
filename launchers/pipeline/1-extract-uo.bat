@rem Extract a character from YOUR UO client into workspace\ and apply the bundled annotations.
@rem Usage: 1-extract-uo.bat [character, default body-400]
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_UO_SOURCE "your UO client folder (with anim.mul / anim.idx)" || exit /b 1
set "CHARACTER=%~1"
if "%CHARACTER%"=="" set "CHARACTER=body-400"
%SM_CLI% extract --game ultima-online --character %CHARACTER% --source "%SPRITEMOTION_UO_SOURCE%" --out "workspace\ultima-online\%CHARACTER%" || exit /b 1
%SM_CLI% status "workspace\ultima-online\%CHARACTER%"
