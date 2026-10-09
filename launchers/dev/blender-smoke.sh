#!/usr/bin/env bash
# Run the headless Blender smoke checks (FK agreement, rig export, camera projection, render placement); results land in workspace/blender-smoke.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_BLENDER "the Blender executable"
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" --python "$SM_BLENDER_TOOLS/tests/smoke_test.py" -- --out workspace/blender-smoke
