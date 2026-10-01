@rem THE launcher: open the Sprite Pose Editor on a dataset.
@rem Usage: sprite-pose-editor.bat [dataset folder]   (default: SPRITEMOTION_DATASET)
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_GODOT "the Godot 4.7 executable (see tools\godot\README.md)" || exit /b 1
set "DATASET=%~1"
if "%DATASET%"=="" set "DATASET=%SPRITEMOTION_DATASET%"
for %%I in ("%DATASET%") do set "DATASET=%%~fI"
start "" "%SPRITEMOTION_GODOT%" --path "%SM_EDITOR%" -- --dataset="%DATASET%"
