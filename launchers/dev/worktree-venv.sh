#!/usr/bin/env bash
# Build workspace/venv for this checkout (a git worktree too), install it editable with the test extras, and fail unless spritemotion imports from this checkout.
# args: [--rebuild]  (default: reuse the venv and refresh the editable install)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
py=$(command -v python3 || command -v python || true)
if [ -z "$py" ]; then echo "[SpriteMotion] No python3 on PATH." >&2; exit 1; fi
exec "$py" tools/worktree-venv/run.py "$@"
