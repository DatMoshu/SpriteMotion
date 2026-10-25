#!/usr/bin/env bash
# Validate external storage and the matching Python environment before starting this or a historical checkout.
# args: [--checkout PATH] [--python PATH] [--paths-only]
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
exec "$_sm_bootstrap" "$SM_ROOT/tools/storage/run.py" startup "$@"
