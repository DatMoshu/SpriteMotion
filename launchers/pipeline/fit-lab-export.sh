#!/usr/bin/env bash
# Export a pack for Fit Lab into workspace/ultima-online/fit-lab/<pack> (body, items, manifest) and print the result.
# args: --pack <pack> [--force]
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
sm_require SPRITEMOTION_BLENDER "the Blender executable"
"$SPRITEMOTION_PYTHON" tools/fit-lab/run.py export "$@"
