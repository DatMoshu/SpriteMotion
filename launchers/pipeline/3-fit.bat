@echo off
rem Export your model's rig from Blender, then fit one sequence to the dataset's annotations (writes workspace\fits\rig.json and workspace\fits\<sequence>.json).
rem args: <sequence, e.g. action-022> [approved|independent|all]
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
if "%~1"=="" (
    echo Usage: %~nx0 ^<sequence^> [approved^|independent^|all]
    exit /b 1
)
set "TARGETS=%~2"
if "%TARGETS%"=="" set "TARGETS=approved"
if not exist workspace\fits mkdir workspace\fits
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% "%SPRITEMOTION_BLEND%" --python "%SM_BLENDER_TOOLS%\export_rig.py" -- --out workspace\fits\rig.json %SM_ARMATURE_ARG% || exit /b 1
%SM_CLI% fit "%SPRITEMOTION_DATASET%" --sequence %~1 --rig workspace\fits\rig.json --mapping "%SPRITEMOTION_MAPPING%" --targets %TARGETS% --out "workspace\fits\%~1.json"
