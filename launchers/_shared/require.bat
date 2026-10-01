@rem Usage: call "%~dp0..\_shared\require.bat" VARIABLE "what it is" || exit /b 1
@echo off
setlocal EnableDelayedExpansion
set "value=!%~1!"
if not defined value (
    echo [SpriteMotion] %~1 is not set: %~2
    echo                Set it in launchers\_shared\config.bat or as an environment variable.
    exit /b 1
)
exit /b 0
