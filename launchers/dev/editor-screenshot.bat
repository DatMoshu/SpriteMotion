@rem Capture the editor on a dataset to workspace\screenshots\editor.png.
@rem Usage: editor-screenshot.bat [dataset]   (default: the sample character)
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_GODOT "the Godot 4.7 executable" || exit /b 1
set "DATASET=%~1"
if "%DATASET%"=="" set "DATASET=examples\sample-character"
for %%I in ("%DATASET%") do set "DATASET=%%~fI"
if not exist workspace\screenshots mkdir workspace\screenshots
"%SPRITEMOTION_GODOT%" --path "%SM_EDITOR%" -- --dataset="%DATASET%" --capture="%SM_ROOT%\workspace\screenshots\editor.png"
echo Wrote workspace\screenshots\editor.png
