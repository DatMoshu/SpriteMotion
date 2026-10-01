@rem Saved versions of your model (SPRITEMOTION_BLEND): when, what made each one, and its scores.
@rem Usage: versions.bat                 list
@rem        versions.bat restore <N>     make version N current again (the current one is kept)
@rem Earlier animation passes also stay inside the .blend as actions named <action>.v001, .v002 ...
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
if /i "%~1"=="restore" (
    %SM_CLI% versions restore "%SPRITEMOTION_BLEND%" --version %~2
) else (
    %SM_CLI% versions list "%SPRITEMOTION_BLEND%"
)
