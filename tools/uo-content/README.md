# SpriteMotion content studio

This is the active UO item-authoring path. It uses the **shared UO_Model3D v13 model** from `UO_Model3D-main.zip`, with its original actions and bone scale inheritance. SpriteMotion's older fitted model is historical research, not the default for new content.

## Start

Requires Python 3.10+, Pillow, NumPy and Blender 4.2+. Set `SPRITEMOTION_BLENDER` if Blender is not on PATH or in the usual Windows install directory.

```powershell
python tools/uo-content/pipeline.py setup --source <extracted-UO_Model3D-main-folder>
python tools/uo-content/studio.py
```

Open http://127.0.0.1:8772. Windows users can run `launchers/editor/content-studio.bat` after setup. The setup command installs the supplied scene and its reviewed render/bind/VD tools into `workspace/ultima-online/canonical-model`, retaining source hashes and attribution. It does not use the older v12 archive. Do not run setup while builds are active.

## Inputs

* **3D model:** GLB, glTF, FBX, OBJ, STL or Blender mesh. The studio uploader accepts self-contained GLB/FBX/STL/BLEND. Use the CLI for OBJ/glTF with adjacent textures/material/bin files. Imported meshes are flattened at their current shape, placed at the selected body region, and bound to the canonical rig. A helmet is rigidly weighted to the head. Clothing uses the supplied surface-weight transfer; cloak/skirt binding uses the supplied cloth templates.
* **Picture:** applied as material artwork to a fitted template. This is not single-image 3D reconstruction. Use a cropped texture/design image; background removal and directional design can be performed in an agent-assisted design task.
* **Text in the studio:** selects/configures a procedural equipment template, recognizes named base colors when no explicit color is supplied, and supports a helmet crest. The visible controls determine equipment type and placement. It is not an unrestricted generative model.
* **Agent-assisted text/picture work:** use the included `uo-content-build` skill. An agent can generate artwork or author new Blender geometry for the requested design, inspect it, then feed that asset to the same tested pipeline. No external 3D generation service or account is assumed.

Automatic fit is a starting placement. Use rotation/scale/offset controls, or fit the object in Blender in the body's rest pose and choose **Keep supplied world coordinates**. Uploaded scenes should contain only the intended item meshes. Imported material base colors and textures are connected to the reference UO lighting; advanced material alpha/procedural effects may need manual adaptation.

Preview builds contain actions 0, 4, 9, 22 and 25 across five stored directions. Full builds contain all 35 actions / 1,050 frames. Jobs run serially and never mix frames from earlier designs. Review exposes eight facings by mirroring three stored views, and body/item visibility switches. Review FPS is not authoritative game timing.

## Outputs and importing

Each job under `workspace/ultima-online/content-studio/jobs/<id>` includes:

* `item.blend`: item mounted on the new rig, editable and with packed images.
* `item.vd`: UOFiddler people/equipment export, available for collaborators.
* `render/clothing`: transparent PNGs and vdtool-compatible canvas metadata.
* `review`: SpriteMotion 256px atlases and a local animation viewer.
* `inventory.png`, `contact-sheet.png`, `validation.json`, scene settings, input provenance and `import-package.zip`.

The renderer expands the viewport to 256×256, anchor (128,192), preserving 36 pixels/metre and camera orientation. This prevents the tight reference canvas from clipping larger equipment. The original body image remains a comparison/occlusion reference. It is not baked into the item layer. All exported VD frame alphas and anchors are checked through SpriteMotion's independent MUL decoder.

For UOFiddler, import the full `item.vd` into an unused people/equipment animation slot. For classic clients, stage patched copies:

```powershell
python tools/uo-content/client_import.py stage --vd <job>/item.vd --client <client-folder> --body <unused-animation-id> --out <new-staging-folder>
python tools/uo-content/equipment.py --job <job> --client <client-folder> --body <unused-animation-id> --graphic <unused-static-graphic-id> --server modernuo
```

The second command also stages inventory art in `art.mul/artidx.mul`, clones a known equipment tiledata record with the new animation ID/name, and generates a cosmetic ModernUO or ServUO item class. It does not invent combat statistics. Both commands reject occupied animation IDs; equipment staging also rejects occupied art/tiledata. Animation ID and static graphic ID are different values. Output goes to new files, with source/output hashes and a verification report. The source client is not modified. A failed staging operation may leave a partial output folder; inspect the error and use a fresh destination after fixing it.

Before live deployment, select the actual client/server and verify its asset routing. `artLegacyMUL.uop` can shadow MUL art; this tool reports that case and provides `inventory.png` for the UOP importer. Body/Equip conversion rules, custom paperdoll gumps and female-body conversion are not automatically authored. Generated server code must be compiled in the target server and tested in-game. The current implementation stages assets; it does not claim a running shard has been updated.

## CLI and verification

```powershell
python tools/uo-content/pipeline.py build --spec tools/uo-content/example-helmet.json
python tools/uo-content/pipeline.py build --spec <item-settings.json> --asset <helmet.glb>
python -m unittest discover -s tools/uo-content -p test_content.py
```

The example settings document shows the minimum fields. Optional `rotate_x/y/z` are degrees; `offset_x/y/z` are metres, `scale` is a uniform multiplier, `fit` is `auto` or `preserve`, `mode` is `preview` or `full`. Every job stores its resolved settings, the original prompt and input hash. A custom generator can hand off a model plus these settings without changing the renderer.

Clipping and empty frames are reported, not hidden. Cloth template binding is included; running a fresh physics cloth bake is not automated here. Mounted occlusion uses the source project's horse proxy/masks and needs visual review. The source file was saved by a later Blender 4.2 patch than the local 4.2.0 test runtime; use the author's version when investigating discrepancies.
