@rem Annotation coverage, review state and fingerprint mismatches for a dataset.
@rem Usage: 2-status.bat [dataset]
@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
set "DATASET=%~1"
if "%DATASET%"=="" set "DATASET=%SPRITEMOTION_DATASET%"
%SM_CLI% validate "%DATASET%" || exit /b 1
%SM_CLI% status "%DATASET%"
