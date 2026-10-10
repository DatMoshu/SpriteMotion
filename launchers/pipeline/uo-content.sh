#!/usr/bin/env bash
# Run the uo-content build pipeline (setup, build, finish, rebuild) and print what it wrote.
# args: setup --source <UO_Model3D folder> | build --spec <json> [--asset <glb>] | finish <job> | rebuild <job> --adjustments <json>
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" tools/uo-content/pipeline.py "$@"
