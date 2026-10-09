#!/usr/bin/env bash
# Open the outfit lab page (workspace/ultima-online/outfit-lab/index.html) in your browser, or say how to build it when it is missing.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
if [ ! -f workspace/ultima-online/outfit-lab/index.html ]; then
    echo "Build the outfit lab first. See games/ultima-online/outfit-lab/README.md" >&2; exit 1
fi
sm_open workspace/ultima-online/outfit-lab/index.html
