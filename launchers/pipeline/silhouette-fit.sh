#!/usr/bin/env bash
# Run the silhouette-constrained fit (prep, then fit) on a dataset and print the fit summary.
# args: prep --dataset <d> --poses <dir> --out <work> | fit --dataset <work> --rig <json> --mapping <json> --camera <json> --out <dir>
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" tools/silhouette-fit/run.py "$@"
