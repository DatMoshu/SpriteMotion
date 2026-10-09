@echo off
rem Run the headless Sprite Pose Editor tests and print the result (report: tools\sprite-pose-editor\tests\output\test-report.json).
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_GODOT_CONSOLE "the Godot 4.7 executable" || exit /b 1
"%SPRITEMOTION_GODOT_CONSOLE%" --headless --path "%SM_EDITOR%" --editor --import --quit >nul 2>&1
"%SPRITEMOTION_GODOT_CONSOLE%" --headless --path "%SM_EDITOR%" --script res://tests/test_editor.gd -- --dataset=tests/fixtures/tiny
