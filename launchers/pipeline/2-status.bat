@echo off
rem Print annotation coverage, review state and fingerprint mismatches for a dataset (exit 1 when it does not validate).
rem args: [dataset]  (default: SPRITEMOTION_DATASET)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
set "DATASET=%~1"
if "%DATASET%"=="" set "DATASET=%SPRITEMOTION_DATASET%"
%SM_CLI% validate "%DATASET%" || exit /b 1
%SM_CLI% status "%DATASET%"
