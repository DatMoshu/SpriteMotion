#!/usr/bin/env bash
# Regenerate examples/sample-character (deterministic; the tests check it matches what is committed).
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_need_python
"$SPRITEMOTION_PYTHON" examples/sample-character/make_sample.py
