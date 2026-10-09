#!/usr/bin/env bash
# Start Content Studio and Fit Lab together for a pack, open both in your browser, and keep them running here until Ctrl+C.
# args: [pack]  (default: SPRITEMOTION_FIT_PACK, else the bundled cc0-starter)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
exec "$SPRITEMOTION_PYTHON" tools/workbench/run.py "$@"
