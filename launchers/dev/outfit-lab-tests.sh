#!/usr/bin/env bash
# Run the outfit-lab unittest suite (games/ultima-online/outfit-lab) and print the result.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
cd games/ultima-online/outfit-lab
"$SPRITEMOTION_PYTHON" -m unittest -q
