@echo off
rem Create .venvs\spritemotion, install SpriteMotion (editable, with test extras) and fetch the tested Godot build into tools\godot unless SPRITEMOTION_GODOT is set.
call "%~dp0..\_shared\common.bat" || exit /b 1
if not exist "%SPRITEMOTION_PYTHON%" (
    py -3 -m venv "%SM_ROOT%\.venvs\spritemotion" 2>nul || python -m venv "%SM_ROOT%\.venvs\spritemotion" || exit /b 1
)
"%SPRITEMOTION_PYTHON%" -m pip install --upgrade pip >nul
"%SPRITEMOTION_PYTHON%" -m pip install -e ".[test]" || exit /b 1
%SM_CLI% --version
if defined SPRITEMOTION_GODOT (
    echo Using Godot at %SPRITEMOTION_GODOT%
) else (
    "%SPRITEMOTION_PYTHON%" "%SM_ROOT%\tools\godot\fetch.py" || exit /b 1
)
