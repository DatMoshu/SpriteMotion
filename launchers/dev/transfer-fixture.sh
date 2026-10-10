#!/usr/bin/env bash
# Regenerate the synthetic transfer-artifact fixture in tests/fixtures/transfer (deterministic, no game data).
# args: [--out dir]  (default: tests/fixtures/transfer)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" tools/transfer-fixture/run.py "$@"
