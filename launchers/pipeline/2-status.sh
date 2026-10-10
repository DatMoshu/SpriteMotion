#!/usr/bin/env bash
# Print annotation coverage, review state and fingerprint mismatches for a dataset (exit 1 when it does not validate).
# args: [dataset]  (default: SPRITEMOTION_DATASET)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
DATASET=${1:-$SPRITEMOTION_DATASET}
"${SM_CLI[@]}" validate "$DATASET"
"${SM_CLI[@]}" status "$DATASET"
