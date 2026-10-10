# Blender render, end to end

From an empty checkout to finished UO sprite frames for one item: install the canonical body, pick a pack part and its
mapping, bring Fit Lab adjustments into the build, choose how many frames to render, and read the outputs.

Every command below was run on a clean worktree (Windows, Blender 4.2.0, `workspace/venv` from
`launchers\dev\worktree-venv.bat`) with the bundled CC0 `shirt`. Times are from that run; yours will differ.

Related: [content studio README](../../tools/uo-content/README.md), [Fit Lab README](../../tools/fit-lab/README.md),
[asset packs](../asset-packs.md), [body occlusion](../body-occlusion.md).

## 0. What you need

| Need | How |
|---|---|
| Python 3.10+ with Pillow and NumPy | `launchers\dev\worktree-venv.bat` creates `workspace\venv` (once per checkout or git worktree) |
| Blender 4.2+ | found through `SPRITEMOTION_BLENDER`, then `tools/blender-runtime`, then PATH, then `%ProgramFiles%` |
| The canonical body | vendored in `third_party/UO_Model3D_v13/`, installed in step 1 |

Run everything from the repository root. The commands below use `workspace\venv\Scripts\python.exe`; on Linux use
`workspace/venv/bin/python`. Nothing here needs a UO client: the vendored body carries no client frames.

## 1. Install the canonical body

```powershell
workspace\venv\Scripts\python.exe tools/uo-content/pipeline.py setup --source third_party/UO_Model3D_v13
```

This copies the model, its render, bind and VD tools into `workspace/ultima-online/canonical-model/` and records source
hashes. It prints that folder and exits 0. Facts about the body you are now rendering with:

- Levy's UO_Model3D at upstream `e9544f6` (see `third_party/UO_Model3D_v13/provenance.json`), 54 bones, rig `UO_Rig`,
  35 actions.
- Direction is a driver, `-d*pi/4`, on the rig's Z rotation. UO frame `i` is scene frame `1 + 3i`.
- Do not run setup while a build is running. Re-running it later changes the renderer fingerprint, and then `rebuild`
  refuses to mix old and new blocks (render a fresh job instead).

Each checkout has its own `workspace/`, so a worktree needs its own setup. The main checkout's copy is untouched.

## 2. Pick a part and its mapping

A pack part reaches the body through an **asset-pack mapping** (`schema: spritemotion.asset-pack`): bones of the pack's
skeleton onto the rig, and part types onto UO equipment layers, with default `offset`, `rotate`, `scale`, `bind` and
`hide_body` per part. Details are in [asset packs](../asset-packs.md).

The bundled CC0 starter set needs no pack purchase. List it:

```powershell
workspace\venv\Scripts\python.exe tools/starter-assets/run.py --list
```

It prints 27 lines, `<layer> <id> <kind>`, for example `5 shirt animated`. `animated` items render as sprites;
`paperdoll` items (ring, talisman, bracelet, earrings) have no animation; `mount` is internal. The mapping is
`examples/cc0-starter/outfit-mapping.json`; the parts are the GLBs beside it.

For a licensed pack, the mapping, its generator and every output stay in the sidecar (`SPRITEMOTION_SIDECAR`), never in
the repository. A job names its mapping with `pack_mapping` and the part with `pack_part` in its settings.

## 3. First render: smoke test

```powershell
workspace\venv\Scripts\python.exe tools/starter-assets/run.py shirt --smoke
```

Renders only action 4 (stand), stored direction 0: one frame, about 4 s. It prints the job folder and
`"state": "complete"`. If this works, the body, Blender and the mapping are wired up.

## 4. Coverage: preview, current action, full

| Coverage | Settings | Frames | Use it for |
|---|---|---|---|
| smoke | `actions: [4], blocks: [[4, 0]]` | 1 | does it build at all |
| preview | `mode: preview` (the default) | 125 in 25 blocks (actions 0, 4, 9, 22, 25 x 5 stored directions) | judging a fit |
| current action | `mode: preview` plus `actions: [N]` | one action x 5 directions | iterating on a pose |
| full | `mode: full` | 1,050 in 175 blocks (35 actions x 5 stored directions) | the deliverable |

Preview actions are 0 walk, 4 stand, 9 attack 1h slash, 22 die backward, 25 mounted stand. Directions 0-4 are
stored. 5, 6, 7 are mirrored from 3, 2, 1 (the client does the same), so they are never rendered. `blocks`
(`[[action, direction], ...]`) selects exact action/direction pairs inside the chosen actions.

Preview, the default for the bundled starter command (75 s for the shirt):

```powershell
workspace\venv\Scripts\python.exe tools/starter-assets/run.py shirt
```

Current action or full, from a settings file. The studio's `starters.settings()` produces the settings of a starter
item, including its mapping and your saved Fit Lab adjustments; write them out and edit the coverage:

```powershell
workspace\venv\Scripts\python.exe -c "import json,sys; sys.path.insert(0,'tools/uo-content'); import starters; spec,_=starters.settings('shirt',{'mode':'full'}); json.dump(spec,open('workspace/shirt-full.json','w'))"
workspace\venv\Scripts\python.exe tools/uo-content/pipeline.py build --spec workspace/shirt-full.json --asset examples/cc0-starter/shirt.glb
```

`build` prints the job folder first, then renders. For one action set `"actions": [4]` in the file and leave
`mode` as `preview`. Jobs run serially and never mix frames from earlier designs. A full build of the shirt took
10 min 39 s: 175 blocks, 1,050 frames, `validation.json` with `full_animation_set: true`, no clipped or empty frames.

A settings file for something that is not a pack part (a model you supply) needs only a name, a `part` and
`mode`; see `tools/uo-content/example-helmet.json` and the README's *Inputs*.

## 5. Bring Fit Lab adjustments into the build

Fit Lab saves one document, `lab-adjustments.json` (`common/schemas/fit-adjustments.schema.json`). A build uses it
in three ways.

1. **Snapshot at job creation.** For the CC0 starter, `starters.settings()` reads
   `workspace/ultima-online/fit-lab/cc0-starter/lab-adjustments.json` when it exists and freezes it into the job
   (`fit_adjustments`). For a sidecar pack, the file sits beside the pack's mapping and the job finds it by the
   mapping path. Explicit `fit_adjustments` in the settings win.
2. **Resolution order.** Mapping defaults for the part, replaced by the saved slot values, then item offsets and scoped
   corrections (pack, slot, group, item; all poses, action, direction, action and direction), then job transforms.
   Every block starts again from the untouched geometry, so corrections never accumulate.
3. **Changed blocks only.** After editing the lab, `rebuild` re-renders just the blocks whose resolved fit changed and
   creates a new validated revision; the source job stays as it was.

```powershell
workspace\venv\Scripts\python.exe tools/uo-content/pipeline.py rebuild <job-folder> --adjustments <lab-adjustments.json>
```

It prints the new job folder. In the verified run an adjustment that scales the shirt by 1.04 and lifts it 1 cm
(`{"parts": {"shirt": {"scale": 1.04, "offset": [0, 0, 0.01]}}, "items": {}}`, keyed by part code) re-rendered all 25
blocks of the preview job in 75 s, because every block's fit changed. `rebuild` refuses to run if the canonical model,
renderer, source meshes or palette changed since the job: render a fresh job then.

To create the cc0 lab data and fit interactively:

```powershell
workspace\venv\Scripts\python.exe tools/starter-assets/run.py --prepare-lab
workspace\venv\Scripts\python.exe tools/fit-lab/run.py serve --pack cc0-starter
```

`--prepare-lab` writes body, 20 item GLBs and the manifest to `workspace/ultima-online/fit-lab/cc0-starter/`
(about 10 s). `serve` listens on http://127.0.0.1:8774 (open it in a browser; stop it with Ctrl+C). The lab's **Build item** and **Rebuild changed blocks** buttons
run the same builds as above; the **Blender render** pane shows *Matches the saved fit* or *Fit changed since this
render*. See the [Fit Lab README](../../tools/fit-lab/README.md).

## 6. The frame layout

- Canvas 256 x 256 pixels, anchor (128, 192), 36 pixels per metre, camera orientation preserved. The canvas is larger
  than the original reference one so big equipment (helmets, shields, weapons) is not clipped.
- Five stored directions per action. Review shows eight facings by mirroring three of them.
- UO frame `i` of an action is scene frame `1 + 3i` of that action in the Blender scene.
- Frame PNGs are transparent; the body is a holdout in the render, so body pixels that poke through the item cut
  holes into the item sprite instead of appearing in it. Hide body (outward and inward, per part) controls which body
  faces are removed under the item. See [body occlusion](../body-occlusion.md).

## 7. Outputs

Each job is `workspace/ultima-online/content-studio/jobs/<id>/`:

| File | What it is |
|---|---|
| `render/clothing/frames/<NN_action>/dir<d>/<frame>.png` | the sprite frames (256 x 256) |
| `render/clothing/meta.json` | canvas, anchor and every block's frame list |
| `item.vd` | UOFiddler people/equipment export (the 125 preview frames or the full 1,050) |
| `item.blend` | the item mounted on the rig, editable, images packed |
| `review/a<NN>-d<d>.png` | per action and direction atlas (256 x 512) |
| `contact-sheet.png`, `inventory.png` | overview and inventory art |
| `validation.json` | frame counts, alpha and anchor round trip through the independent MUL decoder, clipped and empty frames |
| `scene-report.json` | build report (hidden body face counts, per action frame counts) |
| `import-package.zip`, `IMPORT-README.txt` | what to hand to a collaborator |
| `job.json`, `pack-mapping.json`, `build.log` | resolved settings, the mapping frozen at creation, the Blender log |

Check `validation.json` before anything else. A good preview build reads `"vd_alpha_and_anchor_roundtrip": true`,
`"clipped_frames": []`, `"empty_frames": []`; `full_animation_set` is `false` until you render the full set.
Clipping and empty frames are reported, never hidden.

To hand a finished job to another tool, export it as a transfer artifact (`tools/transfer-export/run.py`, see
[transfer artifact](../transfer-artifact.md)). To stage it into a client, see the README's *Outputs and importing*.

## 8. What was not verified

- Importing the VD into a client or UOFiddler, and the `client_import.py` / `equipment.py` staging commands: they need
  a UO client, which this run did not have.
- Sidecar (licensed) packs: the mapping generator and the pack files are not in this repository.
- Blender versions other than 4.2.0.
