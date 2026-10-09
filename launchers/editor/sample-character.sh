#!/usr/bin/env bash
# Open the Sprite Pose Editor (a Godot window) on the bundled, redistributable sample character.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
exec "$(dirname "${BASH_SOURCE[0]}")/sprite-pose-editor.sh" "$SM_ROOT/examples/sample-character"
