@echo off
rem Run the silhouette-constrained fit (prep, then fit) on a dataset and print the fit summary.
rem args: prep --dataset <d> --poses <dir> --out <work> | fit --dataset <work> --rig <json> --mapping <json> --camera <json> --out <dir>
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\silhouette-fit\run.py %*
