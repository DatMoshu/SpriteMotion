@rem The whole loop on the procedural sample: build .blend, export rig, fit, key, render, compare.
@rem Output in workspace\sample\.
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
call "%~dp0..\_shared\require.bat" SPRITEMOTION_BLENDER "the Blender executable" || exit /b 1
set "S=examples\sample-character"
set "W=workspace\sample"
set "M=%S%\rig\sample-mapping.json"
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% --python "%S%\build_blend.py" -- --out %W%\sample.blend || exit /b 1
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% %W%\sample.blend --python "%SM_BLENDER_TOOLS%\export_rig.py" -- --out %W%\rig.json || exit /b 1
%SM_CLI% fit %S% --sequence wave --rig %W%\rig.json --mapping %M% --out %W%\wave-fit.json || exit /b 1
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% %W%\sample.blend --python "%SM_BLENDER_TOOLS%\apply_solution.py" -- --solution %W%\wave-fit.json --action wave --mapping %M% --dataset %S% --report %W%\apply-report.json --save %W%\sample-wave.blend || exit /b 1
"%SPRITEMOTION_BLENDER%" %SM_BLENDER_ARGS% %W%\sample-wave.blend --python "%SM_BLENDER_TOOLS%\render_views.py" -- --dataset %S% --sequence wave --out %W%\renders || exit /b 1
%SM_CLI% compare %S% --renders %W%\renders --sequences wave --out %W%\compare.json || exit /b 1
%SM_CLI% sheet %S% --sequence wave --renders %W%\renders --out %W%\wave-sheet.png || exit /b 1
start "" "%W%\wave-sheet.png"
