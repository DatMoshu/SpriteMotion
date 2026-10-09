@echo off
rem Export a pack for Fit Lab into workspace\ultima-online\fit-lab\<pack> (body, items, manifest) and print the result.
rem args: --pack <pack> [--force]
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\fit-lab\run.py export %*
