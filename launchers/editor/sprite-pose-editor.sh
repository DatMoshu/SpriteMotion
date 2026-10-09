#!/usr/bin/env bash
# THE launcher: open the Sprite Pose Editor (a Godot window that opens and returns) on a dataset.
# args: [dataset folder]  (default: SPRITEMOTION_DATASET)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_GODOT "the Godot 4.7 executable (see tools/godot/README.md)"
DATASET=$(cd "${1:-$SPRITEMOTION_DATASET}" && pwd)
nohup "$SPRITEMOTION_GODOT" --path "$SM_EDITOR" -- --dataset="$DATASET" >/dev/null 2>&1 &
