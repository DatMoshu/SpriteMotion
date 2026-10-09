@echo off
rem Run the Fit Lab browser-code tests (node --test in tools\fit-lab\web) and print the result.
call "%~dp0..\_shared\common.bat" || exit /b 1
where node >nul 2>&1 || (echo [SpriteMotion] Node.js is not installed: needed for the Fit Lab web tests.& exit /b 1)
pushd tools\fit-lab\web || exit /b 1
node --test
set "SM_RC=%errorlevel%"
popd
exit /b %SM_RC%
