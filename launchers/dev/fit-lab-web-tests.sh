#!/usr/bin/env bash
# Run the Fit Lab browser-code tests (node --test in tools/fit-lab/web) and print the result.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
command -v node >/dev/null 2>&1 || { echo "[SpriteMotion] Node.js is not installed: needed for the Fit Lab web tests." >&2; exit 1; }
cd tools/fit-lab/web
node --test
