#!/usr/bin/env sh
set -eu
SM_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
SM_PYTHON=${SPRITEMOTION_PYTHON:-"$SM_ROOT/.venvs/spritemotion/bin/python"}
if [ ! -x "$SM_PYTHON" ]; then SM_PYTHON=${SPRITEMOTION_PYTHON:-python3}; fi
SM_PACK=${1:-${SPRITEMOTION_FIT_PACK:-}}
if [ -z "$SM_PACK" ]; then echo 'Usage: fit-lab.sh <pack> (or set SPRITEMOTION_FIT_PACK)' >&2; exit 1; fi
if [ "$#" -gt 0 ]; then shift; fi
cd "$SM_ROOT"
if [ ! -f "workspace/ultima-online/fit-lab/$SM_PACK/manifest.json" ]; then
    echo "No Fit Lab export for $SM_PACK. See tools/fit-lab/README.md." >&2; exit 1
fi
exec "$SM_PYTHON" tools/fit-lab/run.py serve --pack "$SM_PACK" "$@"
