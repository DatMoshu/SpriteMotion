@echo off
rem Check that the generated agent routers (AGENTS.md, Copilot, Cursor) match CLAUDE.md and the skills; exit 1 when one is stale.
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\agents\run.py --check
