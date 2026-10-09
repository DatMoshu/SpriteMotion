#!/usr/bin/env bash
# Export your model's rig from Blender, then fit one sequence to the dataset's annotations (writes workspace/fits/rig.json and workspace/fits/<sequence>.json).
# args: <sequence, e.g. action-022> [approved|independent|all]
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
sm_require SPRITEMOTION_BLENDER "the Blender executable"
if [ "$#" -lt 1 ]; then echo "Usage: $(basename "$0") <sequence> [approved|independent|all]" >&2; exit 1; fi
TARGETS=${2:-approved}
mkdir -p workspace/fits
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" "$SPRITEMOTION_BLEND" --python "$SM_BLENDER_TOOLS/export_rig.py" -- --out workspace/fits/rig.json ${SM_ARMATURE_ARG[@]+"${SM_ARMATURE_ARG[@]}"}
"${SM_CLI[@]}" fit "$SPRITEMOTION_DATASET" --sequence "$1" --rig workspace/fits/rig.json --mapping "$SPRITEMOTION_MAPPING" --targets "$TARGETS" --out "workspace/fits/$1.json"
