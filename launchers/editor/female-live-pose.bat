@echo off
rem Start the live pose editor server on http://127.0.0.1:8768/editor/ and keep it running here until Ctrl+C.
rem args: [--port N]  (default 8768)
call "%~dp0..\_shared\common.bat" || exit /b 1
call "%~dp0..\_shared\need-python.bat" || exit /b 1
"%SPRITEMOTION_PYTHON%" games\ultima-online\region-masks\pose_editor_server.py %*
