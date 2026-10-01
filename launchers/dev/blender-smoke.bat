@rem Headless Blender checks: FK agreement, rig export, camera projection, render placement.
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% --python "%SM_BLENDER_TOOLS%\tests\smoke_test.py" -- --out workspace\blender-smoke
