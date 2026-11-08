#!/usr/bin/env bash
# Create an external checkout environment and install the tested Godot build in shared storage unless SPRITEMOTION_GODOT is set.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
"$_sm_bootstrap" "$SM_ROOT/tools/worktree-venv/run.py"
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
"$SPRITEMOTION_PYTHON" -m spritemotion --version
if [ -n "${SPRITEMOTION_GODOT:-}" ]; then
    echo "Using Godot at $SPRITEMOTION_GODOT"
else
    "$SPRITEMOTION_PYTHON" "$SM_ROOT/tools/godot/fetch.py"
fi
