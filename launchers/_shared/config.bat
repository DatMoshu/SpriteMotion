@rem ---------------------------------------------------------------------------
@rem SpriteMotion launcher settings: the ONLY launcher file you should edit.
@rem An environment variable of the same name always wins over a value here.
@rem Relative paths are relative to the repository root.
@rem ---------------------------------------------------------------------------

@rem Your own Ultima Online client folder (holds anim.mul / anim.idx). Nothing is copied into the repo.
if not defined SPRITEMOTION_UO_SOURCE set "SPRITEMOTION_UO_SOURCE="

@rem Dataset the editor and pipeline launchers use when none is passed.
if not defined SPRITEMOTION_DATASET set "SPRITEMOTION_DATASET=workspace\ultima-online\body-400"

@rem Tools. Leave blank to use what common.bat finds (tools\godot\, Program Files\Blender Foundation\).
if not defined SPRITEMOTION_GODOT set "SPRITEMOTION_GODOT="
if not defined SPRITEMOTION_BLENDER set "SPRITEMOTION_BLENDER="

@rem Your model (a .blend kept in workspace\) and how its rig maps onto the dataset skeleton.
if not defined SPRITEMOTION_BLEND set "SPRITEMOTION_BLEND=workspace\ultima-online\model.blend"
if not defined SPRITEMOTION_ARMATURE set "SPRITEMOTION_ARMATURE="
if not defined SPRITEMOTION_MAPPING set "SPRITEMOTION_MAPPING=games\ultima-online\skeletons\rig-mappings\rigify.json"

@rem Blender timeline: source frame f is keyed at FRAME_START + f * FRAME_STEP.
if not defined SPRITEMOTION_FRAME_START set "SPRITEMOTION_FRAME_START=1"
if not defined SPRITEMOTION_FRAME_STEP set "SPRITEMOTION_FRAME_STEP=4"

@rem Content-store limits: positive values; inputs and editable scenes never expire.
if not defined SPRITEMOTION_MAX_WORK_GB set "SPRITEMOTION_MAX_WORK_GB=5"
if not defined SPRITEMOTION_OUTPUT_DAYS set "SPRITEMOTION_OUTPUT_DAYS=7"
if not defined SPRITEMOTION_KEEP_OUTPUT_JOBS set "SPRITEMOTION_KEEP_OUTPUT_JOBS=10"
