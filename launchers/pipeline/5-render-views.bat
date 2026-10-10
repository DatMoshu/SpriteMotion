@echo off
rem Render an action of your model from every sprite direction through the dataset camera into workspace\renders\<action>\<sequence>.
rem args: <sequence> [action]  (default action: fit_<sequence>)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
if "%~1"=="" (
    echo Usage: %~nx0 ^<sequence^> [action]
    exit /b 1
)
set "ACTION=%~2"
if "%ACTION%"=="" set "ACTION=fit_%~1"
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% "%SPRITEMOTION_BLEND%" --python "%SM_BLENDER_TOOLS%\render_views.py" -- --dataset "%SPRITEMOTION_DATASET%" --sequence %~1 --action "%ACTION%" --out "workspace\renders\%ACTION%" %SM_ARMATURE_ARG% --frame-start %SPRITEMOTION_FRAME_START% --frame-step %SPRITEMOTION_FRAME_STEP%
