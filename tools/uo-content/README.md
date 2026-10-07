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
* **Asset-pack parts:** modular outfit parts from a third-party pack, fitted through that pack's mapping (bones onto the rig, parts onto UO layers). Set `source_files`, `palette` and `pack_mapping` in the job settings; see [docs/asset-packs.md](../../docs/asset-packs.md). Licensed packs, their mappings and batch scripts stay in a local sidecar folder, never in this repository.
* **Text in the studio:** selects/configures a procedural equipment template, recognizes named base colors when no explicit color is supplied, and supports a helmet crest. The visible controls determine equipment type and placement. It is not an unrestricted generative model.
* **Agent-assisted text/picture work:** use the included `uo-content-build` skill. An agent can generate artwork or author new Blender geometry for the requested design, inspect it, then feed that asset to the same tested pipeline. No external 3D generation service or account is assumed.

Automatic fit is a starting placement. Use rotation/scale/offset controls, or fit the object in Blender in the body's rest pose and choose **Keep supplied world coordinates**. Uploaded scenes should contain only the intended item meshes. Imported material base colors and textures are connected to the reference UO lighting; advanced material alpha/procedural effects may need manual adaptation.

Preview builds contain actions 0, 4, 9, 22 and 25 across five stored directions. Full builds contain all 35 actions / 1,050 frames. Jobs run serially and never mix frames from earlier designs. Review exposes eight facings by mirroring three stored views, and body/item visibility switches. Review FPS is not authoritative game timing.

### Fit corrections and selected blocks

Jobs can specify `actions` and optionally exact `blocks` (`[[action, stored_direction], ...]`). Directions are 0–4;
mirrored views share their stored block. Fit-aware settings follow `common/schemas/fit-build.schema.json`.
`fit_item: {id, slot, part}` identifies an item; `fit_adjustments` is a frozen adjustment document. When omitted,
pack jobs look for `lab-adjustments.json` beside their mapping and identify the item from the local lab source list.
Explicit snapshots take precedence. Unmatched item identity is an error when item/group/slot corrections need it.
Saved slot values replace mapping defaults (avoiding double application of a mapping already merged by the sidecar);
legacy item offsets and scoped deltas are then applied. Explicit job transforms add on top.
Every rendered action/direction resolves from the same untouched base geometry; corrections never accumulate.
All enabled final-render masking uses the complete animated body, including the torso. Clothing mode allows
bounded contact tolerance on the garment's own anatomical region, preserving left/right identity; body mode
uses only the renderer's normal depth margin. Per-scope `occlusion` can override this or disable masking.
The build recomputes fitting-body hiding after each block without removing faces from the invisible occluder.
See [body occlusion](../../docs/body-occlusion.md). Existing saved renders require a fresh build.

`python tools/uo-content/pipeline.py rebuild <job> --adjustments <lab-adjustments.json>` compares resolved fits
for every existing block and renders only changed blocks. It creates a new validated revision, preserving the
source build. Untouched VD blocks remain byte-identical; PNG blocks and metadata are merged, then all frames
undergo the usual independent alpha/anchor validation. A failed revision stays under `staging/` and is not promoted.
Job `rebuild` provenance records source/patch IDs, replaced blocks and hashes of untouched VD blocks. Mapping
files are frozen in each new job so a partial rebuild cannot pick up unrelated mapping changes. The editable
scene carries the latest base/bindings; job settings record the per-block corrections.
Rebuilding refuses to mix versions when the canonical model, renderer code, source meshes or palette has changed;
make a fresh build in that case. Jobs record `render_fingerprint` and `source_fingerprints` for this check.
Rigid bindings do not receive the mesh-deforming push-out solver. Masking policy changes do not change the solver's
collision regions for skinned clothes; the separate pristine-body depth pass controls final visibility.

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

To hand a finished job to another tool (GUO's importer) without its folder layout, export it as a transfer artifact:
`python tools/transfer-export/run.py --job <job> --out <new-folder>`. See [Making one](../../docs/transfer-artifact.md#making-one).

Clipping and empty frames are reported, not hidden. Cloth template binding is included; running a fresh physics cloth bake is not automated here. Mounted occlusion uses the source project's horse proxy/masks and needs visual review. The source file was saved by a later Blender 4.2 patch than the local 4.2.0 test runtime; use the author's version when investigating discrepancies.
