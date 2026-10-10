#!/usr/bin/env bash
# Open the Sprite Pose Editor's source project in the Godot editor (starts the editor window and returns).
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_GODOT "the Godot 4.7 executable (see tools/godot/README.md)"
nohup "$SPRITEMOTION_GODOT" --editor --path "$SM_EDITOR" >/dev/null 2>&1 &
