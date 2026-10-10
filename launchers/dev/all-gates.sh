#!/usr/bin/env bash
# Run the three CLAUDE.md checks in order (pytest, outfit-lab unittest, agents check) and exit non-zero if any fails.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
fail=0
"$SPRITEMOTION_PYTHON" -m pytest -q || fail=1
(cd games/ultima-online/outfit-lab && "$SPRITEMOTION_PYTHON" -m unittest -q) || fail=1
"$SPRITEMOTION_PYTHON" tools/agents/run.py --check || fail=1
if [ "$fail" = 0 ]; then echo "All gates passed."; else echo "A gate failed."; fi
exit "$fail"
