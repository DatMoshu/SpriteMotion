@echo off
rem Validate external storage and the matching Python environment before starting this or a historical checkout.
rem args: [--checkout PATH] [--python PATH] [--paths-only]
call "%~dp0..\_shared\common.bat" || exit /b 1
python "%SM_ROOT%\tools\storage\run.py" startup %*
exit /b %errorlevel%
