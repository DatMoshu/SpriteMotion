@echo off
rem Build workspace\venv for this checkout (a git worktree too), install it editable with the test extras, and fail unless spritemotion imports from this checkout.
rem args: [--rebuild]  (default: reuse the venv and refresh the editable install)
call "%~dp0..\_shared\common.bat" || exit /b 1
where py >nul 2>nul
if not errorlevel 1 (
    py -3 tools\worktree-venv\run.py %*
) else (
    python tools\worktree-venv\run.py %*
)
exit /b %errorlevel%
