@echo off
rem Regenerate the synthetic transfer-artifact fixture in tests\fixtures\transfer (deterministic, no game data).
rem args: [--out dir]  (default: tests/fixtures/transfer)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" tools\transfer-fixture\run.py %*
