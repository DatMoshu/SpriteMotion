@echo off
rem Build a shared-area venv for this checkout, install it editable with the test extras, and verify its import path.
rem args: [--rebuild]  (default: reuse the venv and refresh the editable install)
call "%~dp0..\_shared\common.bat" || exit /b 1
where py >nul 2>nul
if not errorlevel 1 (
    py -3 tools\worktree-venv\run.py %*
) else (
    python tools\worktree-venv\run.py %*
)
exit /b %errorlevel%
