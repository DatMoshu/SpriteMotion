#!/usr/bin/env bash
# Create .venvs/spritemotion, install SpriteMotion (editable, with test extras) and fetch the tested Godot build into tools/godot unless SPRITEMOTION_GODOT is set.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
if [ -z "${SM_VENV_PYTHON:-}" ]; then
    python3 -m venv "$SM_ROOT/.venvs/spritemotion"
    SPRITEMOTION_PYTHON=$(sm_find_venv_python)
fi
"$SPRITEMOTION_PYTHON" -m pip install --upgrade pip >/dev/null
"$SPRITEMOTION_PYTHON" -m pip install -e ".[test]"
"$SPRITEMOTION_PYTHON" -m spritemotion --version
if [ -n "${SPRITEMOTION_GODOT:-}" ]; then
    echo "Using Godot at $SPRITEMOTION_GODOT"
else
    "$SPRITEMOTION_PYTHON" "$SM_ROOT/tools/godot/fetch.py"
fi
