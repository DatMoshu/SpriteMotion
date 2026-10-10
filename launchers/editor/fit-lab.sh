#!/usr/bin/env bash
# Start Fit Lab (asset-pack slot fitting and body hiding) for a pack on http://127.0.0.1:8774 and keep it running here until Ctrl+C.
# args: <pack>  (or set SPRITEMOTION_FIT_PACK)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
SM_PACK=${1:-${SPRITEMOTION_FIT_PACK:-}}
if [ -z "$SM_PACK" ]; then echo "Usage: fit-lab.sh <pack> (or set SPRITEMOTION_FIT_PACK)" >&2; exit 1; fi
if [ "$#" -gt 0 ]; then shift; fi
if [ ! -f "workspace/ultima-online/fit-lab/$SM_PACK/manifest.json" ]; then
    echo "No Fit Lab export for $SM_PACK. See tools/fit-lab/README.md." >&2; exit 1
fi
exec "$SPRITEMOTION_PYTHON" tools/fit-lab/run.py serve --pack "$SM_PACK" "$@"
