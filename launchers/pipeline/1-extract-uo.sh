#!/usr/bin/env bash
# Extract a character from YOUR UO client into workspace/ and apply the bundled annotations, then print its status.
# args: [character]  (default: body-400)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
sm_require SPRITEMOTION_UO_SOURCE "your UO client folder (with anim.mul / anim.idx)"
CHARACTER=${1:-body-400}
"${SM_CLI[@]}" extract --game ultima-online --character "$CHARACTER" --source "$SPRITEMOTION_UO_SOURCE" --out "workspace/ultima-online/$CHARACTER"
"${SM_CLI[@]}" status "workspace/ultima-online/$CHARACTER"
