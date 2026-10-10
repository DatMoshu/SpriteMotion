#!/usr/bin/env bash
# Check that the generated agent routers (AGENTS.md, Copilot, Cursor) match CLAUDE.md and the skills; exit 1 when one is stale.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" tools/agents/run.py --check
