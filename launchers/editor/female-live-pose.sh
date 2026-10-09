#!/usr/bin/env bash
# Start the live pose editor server on http://127.0.0.1:8768/editor/ and keep it running here until Ctrl+C.
# args: [--port N]  (default 8768)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
exec "$SPRITEMOTION_PYTHON" games/ultima-online/region-masks/pose_editor_server.py "$@"
