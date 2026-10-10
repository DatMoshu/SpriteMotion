#!/usr/bin/env bash
# Score the silhouette match and build a contact sheet (sprite, render, difference) for one sequence, then open the sheet; scores are also recorded on the model version.
# args: <sequence> [action]  (default action: fit_<sequence>)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
if [ "$#" -lt 1 ]; then echo "Usage: $(basename "$0") <sequence> [action]" >&2; exit 1; fi
ACTION=${2:-fit_$1}
R=workspace/renders/$ACTION
ATTACH=()
if [ -z "${2:-}" ] && [ -f "$SPRITEMOTION_BLEND" ]; then ATTACH=(--attach "$SPRITEMOTION_BLEND" --label "$ACTION"); fi
"${SM_CLI[@]}" compare "$SPRITEMOTION_DATASET" --renders "$R" --sequences "$1" --out "$R/$1.compare.json" ${ATTACH[@]+"${ATTACH[@]}"}
"${SM_CLI[@]}" sheet "$SPRITEMOTION_DATASET" --sequence "$1" --renders "$R" --out "$R/$1.sheet.png"
sm_open "$R/$1.sheet.png"
