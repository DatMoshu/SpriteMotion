#!/usr/bin/env bash
# Capture the Sprite Pose Editor on a dataset to workspace/screenshots/editor.png and print where it went.
# args: [dataset]  (default: examples/sample-character)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_GODOT "the Godot 4.7 executable (see tools/godot/README.md)"
DATASET=$(cd "${1:-examples/sample-character}" && pwd)
mkdir -p workspace/screenshots
"$SPRITEMOTION_GODOT" --path "$SM_EDITOR" -- --dataset="$DATASET" --capture="$SM_ROOT/workspace/screenshots/editor.png"
echo "Wrote workspace/screenshots/editor.png"
