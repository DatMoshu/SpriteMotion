"""Install and enable the SpriteMotion sheet add-on in the Blender that runs this script, and turn off the old
UO Sheet Reference add-on (its files are left alone; see README.md to delete them).

    blender -b --python install_addon.py

Runs without --factory-startup on purpose: it changes your own Blender preferences.
"""
import os
import addon_utils
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
NEW, OLD = "spritemotion_sheet_reference", "uo_sheet_reference"

if OLD in {m.__name__ for m in addon_utils.modules()} and addon_utils.check(OLD)[1]:
    addon_utils.disable(OLD, default_set=True)
    print(f"[SpriteMotion] disabled the old add-on '{OLD}' (its files are still installed)")
bpy.ops.preferences.addon_install(filepath=os.path.join(HERE, NEW + ".py"), overwrite=True)
addon_utils.enable(NEW, default_set=True)
bpy.ops.wm.save_userpref()
print(f"[SpriteMotion] installed and enabled '{NEW}' in Blender {bpy.app.version_string}")
