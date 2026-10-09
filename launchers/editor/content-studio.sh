#!/usr/bin/env bash
# Start Content Studio (build a UO item from a prompt, picture or model) on http://127.0.0.1:8772 and keep it running here until Ctrl+C.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
echo "Open http://127.0.0.1:8772 in your browser. Ctrl+C stops the studio."
exec "$SPRITEMOTION_PYTHON" tools/uo-content/studio.py "$@"
