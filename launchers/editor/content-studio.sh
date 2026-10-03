#!/usr/bin/env sh
set -eu
SM_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
SM_PYTHON=${SPRITEMOTION_PYTHON:-"$SM_ROOT/.venvs/spritemotion/bin/python"}
if [ ! -x "$SM_PYTHON" ]; then SM_PYTHON=${SPRITEMOTION_PYTHON:-python3}; fi
cd "$SM_ROOT"
exec "$SM_PYTHON" tools/uo-content/studio.py "$@"
