#!/usr/bin/env bash
# Open the tracksuit lab page (workspace/ultima-online/tracksuit-lab/index.html) in your browser, or say how to build it when it is missing.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
if [ ! -f workspace/ultima-online/tracksuit-lab/index.html ]; then
    echo "Build with python games/ultima-online/outfit-lab/build_tracksuit.py first." >&2; exit 1
fi
sm_open workspace/ultima-online/tracksuit-lab/index.html
