#!/usr/bin/env bash
# Run the headless Sprite Pose Editor tests and print the result (report: tools/sprite-pose-editor/tests/output/test-report.json).
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_GODOT_CONSOLE "the Godot 4.7 executable"
"$SPRITEMOTION_GODOT_CONSOLE" --headless --path "$SM_EDITOR" --editor --import --quit >/dev/null 2>&1 || true
"$SPRITEMOTION_GODOT_CONSOLE" --headless --path "$SM_EDITOR" --script res://tests/test_editor.gd -- --dataset=tests/fixtures/tiny
