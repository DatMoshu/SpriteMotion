@echo off
rem Run the uo-content build pipeline (setup, build, finish, rebuild) and print what it wrote.
rem args: setup --source <UO_Model3D folder> | build --spec <json> [--asset <glb>] | finish <job> | rebuild <job> --adjustments <json>
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\uo-content\pipeline.py %*
