#!/usr/bin/env bash
# Run the Python test suite (Blender tests run when Blender is found, the UO test when SPRITEMOTION_UO_SOURCE is set).
# args: [pytest arguments]  e.g. -k sample
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" -m pytest tests "$@"
