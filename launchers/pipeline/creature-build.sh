#!/usr/bin/env bash
# Reshape a CC4 base into a creature in headless Blender and save the result as a .blend.
# args: --config <json> --save <out.blend>
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_BLENDER "the Blender executable"
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" --python "$SM_ROOT/tools/creature-build/build.py" -- "$@"
