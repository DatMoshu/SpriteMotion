@echo off
rem Open the Sprite Pose Editor's source project in the Godot editor (starts the editor window and returns).
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_GODOT "the Godot 4.7 executable (see tools\godot\README.md)" || exit /b 1
start "" "%SPRITEMOTION_GODOT%" --editor --path "%SM_EDITOR%"
