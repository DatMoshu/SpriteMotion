#!/usr/bin/env bash
# List the saved versions of your model (SPRITEMOTION_BLEND) with when, what made each one and its scores, or make an earlier one current again.
# args: [restore <N>]  (no argument lists)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
if [ "${1:-}" = restore ]; then
    "${SM_CLI[@]}" versions restore "$SPRITEMOTION_BLEND" --version "${2:-}"
else
    "${SM_CLI[@]}" versions list "$SPRITEMOTION_BLEND"
fi
