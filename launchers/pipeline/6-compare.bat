@echo off
rem Score the silhouette match and build a contact sheet (sprite, render, difference) for one sequence, then open the sheet; scores are also recorded on the model version.
rem args: <sequence> [action]  (default action: fit_<sequence>)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
if "%~1"=="" (
    echo Usage: %~nx0 ^<sequence^> [action]
    exit /b 1
)
set "ACTION=%~2"
if "%ACTION%"=="" set "ACTION=fit_%~1"
set "R=workspace\renders\%ACTION%"
set "ATTACH="
if "%~2"=="" if exist "%SPRITEMOTION_BLEND%" set ATTACH=--attach "%SPRITEMOTION_BLEND%" --label "%ACTION%"
%SM_CLI% compare "%SPRITEMOTION_DATASET%" --renders "%R%" --sequences %~1 --out "%R%\%~1.compare.json" %ATTACH% || exit /b 1
%SM_CLI% sheet "%SPRITEMOTION_DATASET%" --sequence %~1 --renders "%R%" --out "%R%\%~1.sheet.png" || exit /b 1
start "" "%R%\%~1.sheet.png"
