@echo off
rem Open the Sprite Pose Editor (a Godot window) on the bundled, redistributable sample character.
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0sprite-pose-editor.bat" "%~dp0..\..\examples\sample-character"
exit /b %errorlevel%
