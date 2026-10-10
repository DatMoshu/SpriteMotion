#!/usr/bin/env bash
# Open the sci-fi plate armor lab page (workspace/ultima-online/plate-armor-lab/index.html) in your browser, or say how to build it when it is missing.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
if [ ! -f workspace/ultima-online/plate-armor-lab/index.html ]; then
    echo "Build the sci-fi plate armor lab first with python games/ultima-online/outfit-lab/build_plate_armor.py" >&2; exit 1
fi
sm_open workspace/ultima-online/plate-armor-lab/index.html
