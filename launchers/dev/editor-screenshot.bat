@echo off
rem Capture the Sprite Pose Editor on a dataset to workspace\screenshots\editor.png and print where it went.
rem args: [dataset]  (default: examples\sample-character)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_GODOT "the Godot 4.7 executable (see tools\godot\README.md)" || exit /b 1
set "DATASET=%~1"
if "%DATASET%"=="" set "DATASET=examples\sample-character"
for %%I in ("%DATASET%") do set "DATASET=%%~fI"
if not exist workspace\screenshots mkdir workspace\screenshots
"%SPRITEMOTION_GODOT%" --path "%SM_EDITOR%" -- --dataset="%DATASET%" --capture="%SM_ROOT%\workspace\screenshots\editor.png" || exit /b 1
echo Wrote workspace\screenshots\editor.png
