#!/usr/bin/env bash
# Render an action of your model from every sprite direction through the dataset camera into workspace/renders/<action>/<sequence>.
# args: <sequence> [action]  (default action: fit_<sequence>)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_BLENDER "the Blender executable"
if [ "$#" -lt 1 ]; then echo "Usage: $(basename "$0") <sequence> [action]" >&2; exit 1; fi
ACTION=${2:-fit_$1}
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" "$SPRITEMOTION_BLEND" --python "$SM_BLENDER_TOOLS/render_views.py" -- --dataset "$SPRITEMOTION_DATASET" --sequence "$1" --action "$ACTION" --out "workspace/renders/$ACTION" ${SM_ARMATURE_ARG[@]+"${SM_ARMATURE_ARG[@]}"} --frame-start "$SPRITEMOTION_FRAME_START" --frame-step "$SPRITEMOTION_FRAME_STEP"
