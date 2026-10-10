#!/usr/bin/env bash
# Build a whole outfit from a Fit Lab catalogue and composite contact sheets in client layer order (local output, prints a per-slot table).
# args: build|body|composite ... (see tools/whole-outfit/run.py --help)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" tools/whole-outfit/run.py "$@"
