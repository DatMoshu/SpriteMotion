@echo off
call "%~dp0..\_shared\common.bat" || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0content-studio.ps1"
exit /b %errorlevel%
