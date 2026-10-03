# CC0 equipment starter

The catalog covers every entry in SpriteMotion's 25-layer UO equipment table:

- **20 animated slots:** weapons/shields, shoes, pants, shirt, helm, gloves, neck,
  hair, waist, inner torso, face, facial hair, middle torso, arms, cloak, backpack,
  outer torso, outer legs and inner legs.
- **Four paperdoll-only slots:** ring, talisman, bracelet and earrings include source GLBs
  for artwork authoring. They deliberately do not generate a body-animation VD.
- **Mount:** documented as the server's internal mount item. It requires creature animations
  and mounted rider actions, not an equipment mesh; no sample horse or automatic mount importer is claimed.

Sources are [Kenney Mini Dungeon](https://kenney.nl/assets/mini-dungeon),
[Quaternius Modular Character Outfits — Fantasy (free standard)](https://quaternius.com/packs/modularcharacteroutfitsfantasy.html),
and simple original accessories dedicated to CC0. The original accessories are basic fitting examples,
not a commercial-quality outfit collection. See [Kenney's license](License.txt),
[Quaternius's license](License-Quaternius.txt), [supplement license](supplement-license.txt),
and [per-file provenance](provenance.json).

Every GLB includes its textures. No account or asset download is required. Source clothing has exposed
skin faces removed; no geometry from the UO body is bundled. Shirts and tunics intentionally reuse the
same example shape on different layers. These are starting fits, not approved game-ready exports.

## Try a supplied asset

After the normal SpriteMotion Python, Blender and separately supplied UO model setup, open Content Studio,
choose **Bundled CC0 starter**, and click **Build item**. No asset download or file selection is needed.
Restart Content Studio after updating to load the new backend.

Alternatively, run:

```sh
python tools/starter-assets/run.py weapon-sword
```

Run `python tools/starter-assets/run.py --list` for every slot and its route.
For example: `boots`, `shirt`, `hood`, `gloves`, `cloak`, `backpack`, `robe`, `ring`.
Add `--smoke` for a quick idle/direction-0 render. Default previews include walk, idle,
attack, fall and mounted actions. Jobs appear in Content Studio at http://127.0.0.1:8772.
Review placement and occlusion before exporting a full animation; automatic placement is only a starting point.

## Open the starter Fit Lab

```sh
python tools/starter-assets/run.py --prepare-lab
python tools/fit-lab/run.py serve --pack cc0-starter
```

Or use `launchers/editor/workbench.bat cc0-starter` on Windows, or
`sh launchers/editor/workbench.sh cc0-starter` on Linux. The combined launcher prepares a missing
starter lab automatically, then starts both tools. An existing different lab on port 8774 must
be stopped first; it is never silently replaced.

Preparation requires Blender and your separately supplied canonical UO model. All generated body,
reference sprites, fitted GLBs, renders and saved adjustments stay in ignored `workspace/`.
The 20 animated slots appear in the lab. Content Studio exposes all slots and source downloads;
paperdoll/internal entries explain their separate route. Saved starter lab fits are used by starter builds.

## Rebuild the distributable sources

Download/extract the creator's free standard outfit archive, then run Blender with
`tools/starter-assets/prepare_blender.py -- <extracted-pack-root> examples/cc0-starter`.
This script reads only CC0 source files and creates original primitive accessories; it never reads the UO model.
It emits `sources.json` with hashes. Update the matching provenance entries after reviewing regenerated files.

## Add your own assets

1. Start `launchers/editor/content-studio.bat` or `python tools/uo-content/studio.py`.
2. Select the equipment type and upload a self-contained GLB (recommended), FBX, STL or BLEND.
   Include only the item meshes. Pack textures into the GLB before uploading.
3. Build a preview, inspect the item over the reference body, and adjust placement.
4. Render the full animation once the preview is correct. Use the resulting review and import package.

For OBJ/glTF with adjacent resources use the CLI instead:

```sh
python tools/uo-content/pipeline.py build --spec examples/cc0-starter/weapon-sword.json --asset path/to/your-model.glb
```

Fit Lab's **Load fitted GLBs from a folder** accepts already fitted models with the canonical
bone names/weights; it is not a raw model importer. Modular clothing packs need a skeleton/slot
mapping and lab export: see [asset packs](../../docs/asset-packs.md).
GUO's embedded Fit Lab uses that same service and has the same input requirements.

The starter models can also be imported directly into Godot or Blender without UO data.
The UO body, animation backend and client art are not bundled or licensed by this CC0 notice.
