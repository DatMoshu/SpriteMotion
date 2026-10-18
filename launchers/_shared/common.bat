@rem Shared launcher logic. Every launcher starts with:  call "%~dp0..\_shared\common.bat" || exit /b 1
@rem Settings resolve: environment variable > config.bat > the defaults below.
@echo off
for %%I in ("%~dp0..\..") do set "SM_ROOT=%%~fI"
call "%~dp0config.bat"

@rem Prefer the shared-area venv keyed to THIS checkout, then legacy environments.
set "SM_CHECKOUT_VENV="
for /f "delims=" %%V in ('python "%SM_ROOT%\tools\worktree-venv\run.py" --path 2^>nul') do set "SM_CHECKOUT_VENV=%%V"
if not defined SPRITEMOTION_PYTHON if defined SM_CHECKOUT_VENV if exist "%SM_CHECKOUT_VENV%\Scripts\python.exe" set "SPRITEMOTION_PYTHON=%SM_CHECKOUT_VENV%\Scripts\python.exe"
if not defined SPRITEMOTION_PYTHON if exist "%SM_ROOT%\workspace\venv\Scripts\python.exe" set "SPRITEMOTION_PYTHON=%SM_ROOT%\workspace\venv\Scripts\python.exe"
if not defined SPRITEMOTION_PYTHON set "SPRITEMOTION_PYTHON=%SM_ROOT%\.venvs\spritemotion\Scripts\python.exe"
if not defined SPRITEMOTION_GODOT if exist "%SM_ROOT%\tools\godot\Godot_v4.7-stable_win64.exe" set "SPRITEMOTION_GODOT=%SM_ROOT%\tools\godot\Godot_v4.7-stable_win64.exe"
if not defined SPRITEMOTION_GODOT_CONSOLE if exist "%SM_ROOT%\tools\godot\Godot_v4.7-stable_win64_console.exe" set "SPRITEMOTION_GODOT_CONSOLE=%SM_ROOT%\tools\godot\Godot_v4.7-stable_win64_console.exe"
if not defined SPRITEMOTION_GODOT_CONSOLE set "SPRITEMOTION_GODOT_CONSOLE=%SPRITEMOTION_GODOT%"
if not defined SPRITEMOTION_BLENDER for /d %%D in ("%ProgramFiles%\Blender Foundation\Blender *") do if exist "%%~D\blender.exe" set "SPRITEMOTION_BLENDER=%%~D\blender.exe"

set "SM_EDITOR=%SM_ROOT%\tools\sprite-pose-editor"
set "SM_BLENDER_TOOLS=%SM_ROOT%\tools\blender"
set SM_CLI="%SPRITEMOTION_PYTHON%" -m spritemotion
@rem --factory-startup keeps your own Blender add-ons out of headless runs.
set "SM_BLENDER_ARGS=-b --factory-startup"
set "SM_ARMATURE_ARG="
if defined SPRITEMOTION_ARMATURE set "SM_ARMATURE_ARG=--armature %SPRITEMOTION_ARMATURE%"
cd /d "%SM_ROOT%"
exit /b 0
