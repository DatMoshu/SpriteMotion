# Export to GUO: from a finished job to staged client data

Take a finished SpriteMotion build job, export it as a **transfer artifact** (the versioned hand-off format), check it,
and see which route reaches [GUO](https://github.com/DatMoshu/GodotUO) (or a classic client) today. The example is the
bundled CC0 `shirt`, rendered with full coverage. No UO client data is involved.

Reference: [transfer artifact](../transfer-artifact.md) (format and reader), [Blender render, end to end](blender-render-end-to-end.md)
(how the job is made), [Content Studio README](../../tools/uo-content/README.md) ("Outputs and importing"),
[GUO integration plan](../guo-integration-plan.md).

## Status, read this first

| Step | State |
|---|---|
| Job -> transfer artifact (`tools/transfer-export`) | works, verified below |
| Read it back (`spritemotion.transfer`, standard library only) | works, verified below |
| Artifact -> GUO staged data (`uopack from-job`) | **not built.** GUO has no transfer loader yet; its `tools/uopack` knows `unpack`, `pack`, `roundtrip`, `from-dreadcrest` and `from-outfit-lab`, not a SpriteMotion job |
| Job -> classic client through `item.vd` | works (SpriteMotion side), needs a client; not run here |

So an artifact is a finished, checked package that waits for GUO's importer. Keep it, and use the `.vd` route (step 5)
if you need the item in a client today. GUO's `docs/data_formats.md` section 35 is "Shard host profiles", not this
import; no GUO section describes the transfer import yet.

## Prerequisites

- A worktree venv: `launchers\dev\worktree-venv.bat` (Pillow is in it; the exporter needs `spritemotion[imaging]`).
- The canonical body installed (`pipeline.py setup`, step 1 of the Blender guide).
- A **complete** job. For GUO use `mode: full`: GUO's first importer refuses `coverage: preview` and needs every stored
  direction 0-4 for each imported action. A preview job exports fine, it just is not importable there.

## Steps

All commands run from the repository root. `workspace\venv\Scripts\python.exe` is the venv Python.

### 1. Render a full job

```powershell
workspace\venv\Scripts\python.exe -c "import json,sys; sys.path.insert(0,'tools/uo-content'); import starters; spec,_=starters.settings('shirt',{'mode':'full'}); json.dump(spec,open('workspace/shirt-full.json','w'))"
workspace\venv\Scripts\python.exe tools/uo-content/pipeline.py build --spec workspace/shirt-full.json --asset examples/cc0-starter/shirt.glb
```

`build` prints the job folder first, then renders (about 10 minutes: 175 blocks, 1,050 frames). The job is done when
its `status.json` reads `"state": "complete"`. Check `validation.json` before exporting.

### 2. Export the transfer artifact

```powershell
launchers\pipeline\transfer-export.bat --job <job folder> --out <new empty folder> --source-redistribution public --source-license CC0-1.0 --rendered-redistribution public --rendered-license CC0-1.0
```

(`transfer-export.sh` on Linux; both run `tools/transfer-export/run.py`.) It prints `Wrote 1052 files to <folder>`:
`transfer.json`, `validation.json`, and 1,050 cropped frames in `frames/`.

- The job is only read. `--out` must be new or empty and outside the job; a failed export removes what it wrote.
- The job records no licence. The redistribution classes default to `unknown`; say what is true. Use the CC0 values
  above only for the bundled starter. For anything built from a licensed pack, or from client data, use `private` or
  `restricted`, and keep the artifact out of git.
- The exporter finishes by calling `spritemotion.transfer.read` on the result. If it exits 0, the artifact is valid.

### 3. Check it yourself

```powershell
workspace\venv\Scripts\python.exe -c "from spritemotion import transfer; a=transfer.read('<artifact folder>'); print(a.identity, len(a.actions)); r=a.resolve(4,6,0); print(r.mirrored, r.crop, r.centre)"
```

Expected for the verified run: `{'project_id': 'spritemotion', 'item_id': 'shirt', 'slot': 'Shirt', 'source_job': '...'}`,
`35` actions, and `True Crop(left=117, top=141, right=138, bottom=167) (11, 25)`: facing 6 is stored direction 2
mirrored about x = 128. Then read three fields of `transfer.json` that GUO's importer cares about:

| Field | Verified value | What GUO does with it |
|---|---|---|
| `animation.coverage` | `full` | `preview` is refused |
| stored directions in `frames` | 0, 1, 2, 3, 4 for every action | 5-7 are the mirror of 3, 2, 1 (`animation.mirror_map`); do not render them |
| `pixels.alpha` | `binary` | GUO stores 1-bit transparency, so binary alpha imports without loss |
| `pixels.quantization` | `none` | the importer quantizes (see below) |

Frame counts: 1,050 frames, none empty, `acceptance.known_failures` empty.

### 4. What GUO will have to do to your pixels

The artifact holds true-colour PNGs. UO animation frames are palette indices, one palette of at most 256 colours per
(action, stored direction) and 15-bit colour. In the verified run **167 of the 175 groups exceed 256 distinct colours**
(the maximum was 1,456), so GUO's importer has to quantize, the same way its `uopack pack` builds a palette (median
cut past 256 colours) for new frames. Expect small colour shifts on shaded cloth. If you need exact control, quantize
yourself before you hand the artifact over; the exporter deliberately does not.

Each frame's PNG is cropped to its alpha box. Its `centre` is `(128 - left, 192 - bottom)`, which is the anchor offset
the animation entry stores. The centre can be negative.

### 5. Reach a client today: the `.vd` route

For the classic client the job's own files are used, not the artifact. UOFiddler: import `item.vd` into an unused
people/equipment slot. Staged copies of a client:

```powershell
workspace\venv\Scripts\python.exe tools/uo-content/client_import.py stage --vd <job>/item.vd --client <client folder> --body <unused animation id> --out <new staging folder>
workspace\venv\Scripts\python.exe tools/uo-content/equipment.py --job <job> --client <client folder> --body <unused animation id> --graphic <unused static graphic id> --server modernuo
```

Animation id and static graphic id are different values. Both commands reject occupied ids, write new files only and
leave the source client untouched. Both need a UO client; this guide's run had none, so they are **not verified here**.
See the Content Studio README for what they do not author (custom paperdoll gumps, Body/Equip conversion, female body).

GUO itself stages content through its own `tools/uopack` and `tools/uodata_write` (the `.vd` and the artifact are not
inputs yet). When `uopack from-job <artifact folder>` lands, step 2's artifact is its input.

## Expected output

```
Wrote 1052 files to <artifact folder>
<artifact folder>/transfer.json
<artifact folder>/validation.json
<artifact folder>/frames/a00-d0-f0.png ... (1,050 files, 256x256 canvas crops)
```

## Common mistakes

- **Exporting a preview job for GUO.** It reads fine and GUO refuses it. Render `mode: full` (step 1).
- **Leaving redistribution at `unknown` and then sharing.** Say what is true; `unknown` means "do not redistribute".
- **Committing the artifact.** Jobs built from client frames or a licensed pack stay local. Only CC0 starter output is
  safe to share.
- **Expecting the exporter to quantize.** It does not (`quantization: none`); the colour counts above are real.
- **`--out` inside the job, or not empty.** Refused. Use a new folder beside it.
- **Rendering directions 5-7.** They are mirrors; the reader accepts only the map `5->3, 6->2, 7->1`.
- **Running GUO's importer.** There is none yet. Do not wait for it to fail; check GUO's `tools/uopack/README.md`.

## What was verified, and what was not

Verified on a clean worktree (Windows, Blender 4.2.0, 2026-10-10): the full shirt build, the export (1,050 frames,
coverage `full`, binary alpha, no empty frames, no known failures), `spritemotion.transfer.read` on the result, the
mirror resolve above, and the colour-count figures.

Not verified: any GUO-side read of the artifact (GUO has no loader, so GUO's `uodata_write` and `uopack` tests could not
take a real export as input), the `client_import.py` / `equipment.py` commands (no UO client), a shard.
