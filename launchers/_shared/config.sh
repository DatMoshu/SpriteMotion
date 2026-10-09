# SpriteMotion launcher settings for the .sh launchers (the twin of config.bat).
# Edit config.local.sh (git-ignored) for your machine; keep this file as the shared defaults.
# Settings resolve: environment variable > config.local.sh > this file. Relative paths are relative to the repository root.

# Your own Ultima Online client folder (holds anim.mul / anim.idx). Nothing is copied into the repo.
SPRITEMOTION_UO_SOURCE=""

# Dataset the editor and pipeline launchers use when none is passed.
SPRITEMOTION_DATASET="workspace/ultima-online/body-400"

# Tools. Leave blank to use what common.sh finds (tools/godot/, blender on PATH, Program Files, /Applications).
SPRITEMOTION_GODOT=""
SPRITEMOTION_BLENDER=""

# Your model (a .blend kept in workspace/) and how its rig maps onto the dataset skeleton.
SPRITEMOTION_BLEND="workspace/ultima-online/model.blend"
SPRITEMOTION_ARMATURE=""
SPRITEMOTION_MAPPING="games/ultima-online/skeletons/rig-mappings/rigify.json"

# Blender timeline: source frame f is keyed at FRAME_START + f * FRAME_STEP.
SPRITEMOTION_FRAME_START=1
SPRITEMOTION_FRAME_STEP=4
