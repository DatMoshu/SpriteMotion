# Third-party notices

SpriteMotion's own code, schemas, documentation and annotations are under the
MIT license in [LICENSE](LICENSE). The repository does not bundle any
third-party software or content. The items below are dependencies you install
yourself, or software the tools talk to.

## Contributed code

The outfit-lab `--config` item lists, the `Bodyconv.def` reader in
`games/ultima-online/region-masks/uo.py`, the `.vd` export and paperdoll gump
scripts in `games/ultima-online/outfit-lab/` (`atlas_to_vd.py`,
`build_item.py`, `merge_items.py`, `make_gump.py`, `make_gump_cloak.py`,
`uo_vd_writer.py`, `vd.py`) and `tools/vd/` were contributed by Levy and are
included with his permission.

## Runtime dependencies (installed by pip)

| Package | Use | License |
|---|---|---|
| [NumPy](https://numpy.org/) | arrays, fitting | BSD-3-Clause |
| [Pillow](https://python-pillow.org/) | PNG reading and writing | MIT-CMU (HPND) |

The local live female pose editor additionally uses Three.js 0.180.0 (MIT).
Its pinned runtime and license are installed in the ignored workspace, not
redistributed with the repository source.

## Test dependencies

| Package | License |
|---|---|
| [pytest](https://pytest.org/) | MIT |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | MIT |

## Applications (not redistributed)

| Application | Use | License |
|---|---|---|
| [Godot Engine 4.7](https://godotengine.org/) | runs the Sprite Pose Editor; place the executable in `tools/godot/` | MIT |
| [Blender 4.2 LTS or 5.2 LTS](https://www.blender.org/) | runs the scripts in `tools/blender/` and the game Blender add-ons | GPL-2.0-or-later |

The Blender scripts use Blender's Python API (`bpy`). If you redistribute a
modified version of them together with Blender, check the
[Blender license FAQ](https://www.blender.org/about/license/) for how the GPL
applies to scripts. The Godot editor project in `tools/sprite-pose-editor/`
uses only Godot's built-in nodes and fonts.

## Games

Game names (for example *Ultima Online*) are trademarks of their respective
owners. SpriteMotion is not affiliated with or endorsed by them. The
repository contains no game data. Adapters read files from an installation
the user supplies, and the output stays in the gitignored `workspace/`
folder. The bundled annotations are coordinate data made by contributors.
They contain no pixels from any game.
