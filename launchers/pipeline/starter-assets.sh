#!/usr/bin/env bash
# Build the bundled CC0 starter equipment (or export it to Fit Lab with --prepare-lab) and print what it produced.
# args: [item] [--list] [--prepare-lab] [--smoke]
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" tools/starter-assets/run.py "$@"
