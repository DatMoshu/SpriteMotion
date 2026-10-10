@echo off
rem List the saved versions of your model (SPRITEMOTION_BLEND) with when, what made each one and its scores, or make an earlier one current again.
rem args: [restore <N>]  (no argument lists)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
if /i "%~1"=="restore" (
    %SM_CLI% versions restore "%SPRITEMOTION_BLEND%" --version %~2
) else (
    %SM_CLI% versions list "%SPRITEMOTION_BLEND%"
)
