#!/usr/bin/env bash
# Export a finished uo-content build job as a transfer artifact (transfer.json plus cropped frames) and read it back to check it.
# args: --job <job dir> --out <new empty dir>
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" tools/transfer-export/run.py "$@"
