@echo off
rem Key a fit into your model as action fit_<sequence> and report the reprojection error Blender produces (saves into SPRITEMOTION_BLEND, keeping the previous file in <model>.versions).
rem args: <sequence> ["note for this version"]
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
if "%~1"=="" (
    echo Usage: %~nx0 ^<sequence^> ["note"]
    exit /b 1
)
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% "%SPRITEMOTION_BLEND%" --python "%SM_BLENDER_TOOLS%\apply_solution.py" -- --solution "workspace\fits\%~1.json" --action "fit_%~1" %SM_ARMATURE_ARG% --mapping "%SPRITEMOTION_MAPPING%" --dataset "%SPRITEMOTION_DATASET%" --frame-start %SPRITEMOTION_FRAME_START% --frame-step %SPRITEMOTION_FRAME_STEP% --report "workspace\fits\%~1.apply-report.json" --save "%SPRITEMOTION_BLEND%" --note "%~2"
