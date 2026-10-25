@echo off
rem Create an external checkout environment and install the tested Godot build in shared storage unless SPRITEMOTION_GODOT is set.
call "%~dp0..\_shared\common.bat" || exit /b 1
python "%SM_ROOT%\tools\worktree-venv\run.py" || exit /b 1
%SM_CLI% --version
if defined SPRITEMOTION_GODOT (
    echo Using Godot at %SPRITEMOTION_GODOT%
) else (
    "%SPRITEMOTION_PYTHON%" "%SM_ROOT%\tools\godot\fetch.py" || exit /b 1
)
