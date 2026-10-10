#!/usr/bin/env bash
# Open the overalls lab page (workspace/ultima-online/overalls-lab/index.html) in your browser, or say how to build it when it is missing.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
if [ ! -f workspace/ultima-online/overalls-lab/index.html ]; then
    echo "Build the overalls lab first with python games/ultima-online/outfit-lab/build_overalls.py" >&2; exit 1
fi
sm_open workspace/ultima-online/overalls-lab/index.html
