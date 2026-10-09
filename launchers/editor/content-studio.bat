@echo off
rem Start Content Studio (build a UO item from a prompt, picture or model) on http://127.0.0.1:8772 and keep it running here until Ctrl+C.
call "%~dp0..\_shared\common.bat" || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0content-studio.ps1"
exit /b %errorlevel%
