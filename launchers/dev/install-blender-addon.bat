@echo off
rem Install the SpriteMotion sheet add-on into your Blender (SPRITEMOTION_BLENDER) and enable it; this changes your Blender preferences.
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
"%SPRITEMOTION_BLENDER%" -b --python "%SM_ROOT%\games\ultima-online\blender\install_addon.py"
