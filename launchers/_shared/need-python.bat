@rem Usage: call "%~dp0..\_shared\need-python.bat" || exit /b 1
@echo off
if exist "%SPRITEMOTION_PYTHON%" exit /b 0
echo [SpriteMotion] No Python environment at %SPRITEMOTION_PYTHON%
echo                Run launchers\pipeline\0-setup.bat first.
exit /b 1
