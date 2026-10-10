@echo off
rem Reshape a CC4 base into a creature in headless Blender and save the result as a .blend.
rem args: --config <json> --save <out.blend>
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% --python "%SM_ROOT%\tools\creature-build\build.py" -- %*
