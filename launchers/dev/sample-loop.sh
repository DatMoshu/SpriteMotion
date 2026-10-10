#!/usr/bin/env bash
# Run the whole loop on the procedural sample (build .blend, export rig, fit, key, render, compare) into workspace/sample, then open the wave sheet.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
sm_require SPRITEMOTION_BLENDER "the Blender executable"
S=examples/sample-character
W=workspace/sample
M=$S/rig/sample-mapping.json
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" "$S/build_blend.py" -- --out "$W/sample.blend"
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" "$W/sample.blend" --python "$SM_BLENDER_TOOLS/export_rig.py" -- --out "$W/rig.json"
"${SM_CLI[@]}" fit "$S" --sequence wave --rig "$W/rig.json" --mapping "$M" --out "$W/wave-fit.json"
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" "$W/sample.blend" --python "$SM_BLENDER_TOOLS/apply_solution.py" -- --solution "$W/wave-fit.json" --action wave --mapping "$M" --dataset "$S" --report "$W/apply-report.json" --save "$W/sample-wave.blend"
"$SPRITEMOTION_BLENDER" "${SM_BLENDER_ARGS[@]}" "$W/sample-wave.blend" --python "$SM_BLENDER_TOOLS/render_views.py" -- --dataset "$S" --sequence wave --out "$W/renders"
"${SM_CLI[@]}" compare "$S" --renders "$W/renders" --sequences wave --out "$W/compare.json"
"${SM_CLI[@]}" sheet "$S" --sequence wave --renders "$W/renders" --out "$W/wave-sheet.png"
sm_open "$W/wave-sheet.png"
