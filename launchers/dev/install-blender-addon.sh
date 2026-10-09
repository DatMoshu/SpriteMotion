#!/usr/bin/env bash
# Install the SpriteMotion sheet add-on into your Blender (SPRITEMOTION_BLENDER) and enable it; this changes your Blender preferences.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
sm_require SPRITEMOTION_BLENDER "the Blender executable"
"$SPRITEMOTION_BLENDER" -b --python "$SM_ROOT/games/ultima-online/blender/install_addon.py"
