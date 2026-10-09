#!/usr/bin/env bash
# Key a fit into your model as action fit_<sequence> and report the reprojection error Blender produces (saves into SPRITEMOTION_BLEND, keeping the previous file in <model>.versions).
# args: <sequence> ["note for this version"]
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_BLENDER "the Blender executable"
if [ "$#" -lt 1 ]; then echo "Usage: $(basename "$0") <sequence> [\"note\"]" >&2; exit 1; fi
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" "$SPRITEMOTION_BLEND" --python "$SM_BLENDER_TOOLS/apply_solution.py" -- --solution "workspace/fits/$1.json" --action "fit_$1" ${SM_ARMATURE_ARG[@]+"${SM_ARMATURE_ARG[@]}"} --mapping "$SPRITEMOTION_MAPPING" --dataset "$SPRITEMOTION_DATASET" --frame-start "$SPRITEMOTION_FRAME_START" --frame-step "$SPRITEMOTION_FRAME_STEP" --report "workspace/fits/$1.apply-report.json" --save "$SPRITEMOTION_BLEND" --note "${2:-}"
