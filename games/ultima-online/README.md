# Ultima Online (classic 2D client)

SpriteMotion support for mobile animations from the classic client:
`anim.mul` / `anim.idx` and the UOP containers (`AnimationFrame*.uop`).

| Character | Id | Sequences | Frames | Annotations |
|---|---|---|---|---|
| Human male base, body 400 (0x190) | `body-400` | 35 actions (`action-000` … `action-034`) | 1,680 in 8 directions | all 1,680 have estimates; **6 approved corrections** |
| Human female base, body 401 (0x191) | `body-401` | 35 actions | extractable | none yet |
| Gargoyle male, body 666 (0x29A) | `body-666` | 52 groups (UOP) | 4,160 in 8 directions | none yet |
| Gargoyle female, body 667 (0x29B) | `body-667` | UOP | extractable (not yet tried) | none yet |

**No game data is in this repository.** You extract frames from your own
client installation. The frames stay in `workspace/` and must not be
redistributed.

## Extract

```bat
set SPRITEMOTION_UO_SOURCE=<your UO client folder>
launchers\pipeline\1-extract-uo.bat              :: body-400 by default; pass body-401 for the female base
```

or

```sh
python -m spritemotion extract --game ultima-online --character body-400 \
    --source "<UO folder>" --out workspace/ultima-online/body-400
```

Expected result for body 400: `1680 frames, 1680 annotated, 6 approved,
0 fingerprint mismatches`. If some poses report mismatches, your client's
frames differ from the ones the annotations were drawn on. The report lists
exactly which frames. Review those poses in the editor before using them.

Supported:

- classic `anim.mul`/`anim.idx` (file 1, the "people" action group)
- UOP containers `AnimationFrame1..6.uop` (compression none, zlib, zlib+BWT),
  including `AnimationSequence.uop` action redirects

Which one a body is read from follows ClassicUO: UOP when `mobtypes.txt`
flags the body for UOP (0x10000), otherwise MUL. A profile's `anim_source`
(`auto`, `mul`, `uop`) or the `SPRITEMOTION_UO_ANIM_SOURCE` environment
variable overrides it. Each frame records the file it came from.

Not yet supported: `anim2`–`anim5.mul`, `Body.def` / `Bodyconv.def`
substitutions, and hues. The adapter stops with a clear error instead of
guessing. Details: [research/uo-conventions.md](research/uo-conventions.md#uop-animations-animationframeuop).

## What is here

| Path | Contents |
|---|---|
| `game.json` | adapter and character list |
| `extraction/` | `uo_anim.py` (MUL decoder, source selection), `uo_uop.py` (UOP container), `uo_adapter.py` (placement, mirroring, fingerprints) |
| `profiles/` | `body-400.json`, `body-401.json`, `body-666.json`, `body-667.json` (canvas, directions, camera, Blender timeline), `human-actions.json` / `gargoyle-actions.json` (action names), `cameras/` (camera candidates) |
| `skeletons/` | `humanoid-20.json` (20 joints, A/B limb chains) and `rig-mappings/` for Rigify (FK) and Mixamo rigs |
| `annotations/body-400/` | `estimates/` (35 files), `corrections/action-022.json`, `MIGRATION.json` |
| `migration/` | the script that converted the earlier UO Roto data ([notes](research/migration.md)) |
| `blender/` | the *SpriteMotion Sheet Reference* Blender add-on ([README](blender/README.md)) |
| `recipes/` | [reconstructing body 400](recipes/reconstruct-body-400.md), [annotation review](recipes/review-annotations.md) |
| `research/` | [conventions](research/uo-conventions.md), [findings so far](research/findings.md), [migration](research/migration.md) |

## Canvas and directions

Frames are placed on a 256×256 canvas. Each frame's ground origin lands on
pixel (128, 192), the same way ClassicUO places a mobile on its tile.
`anim.mul` stores 5 of the 8 facings, and the client mirrors three of them at
draw time (mirror axis x = 127.5):

| id | name | stored index | mirrored from |
|---|---|---|---|
| 0 | N | 3 | W (6) |
| 1 | NE | 2 | SW (5) |
| 2 | E | 1 | S (4) |
| 3 | SE | 0 | stored |
| 4 | S | 1 | stored |
| 5 | SW | 2 | stored |
| 6 | W | 3 | stored |
| 7 | NW | 4 | stored |

Details: [research/uo-conventions.md](research/uo-conventions.md).

## State of the annotations

The body-400 annotations came from the earlier *UO Roto* joint lab. See
[research/migration.md](research/migration.md) for how.

- **Action 22 (`death_forward`), SE:** 6 poses corrected and approved by a
  person. These are the only approved poses. Their manual A/B limb labels are
  provisional per view.
- **Action 22, other stored views:** manual estimates (independent, not
  approved).
- **Action 22, mirrored views:** mirrors of those.
- **Every other action:** rig projections from a fitted draft model,
  registered to the sprite bounds. They are labelled `independent: false`.
  Use them as starting points for correction, never as evidence for a fit.

So only one sequence currently has approved targets. The most useful
contribution is correcting and approving more poses, especially two or more
directions of the same frames. See
[recipes/review-annotations.md](recipes/review-annotations.md).

## Camera

The dataset camera (`profiles/cameras/ground-grid.json`) reproduces the
client's ground grid exactly. It is **not proven** to be the projection the
character art was made with. A candidate with a smaller depth term
(`character-depth-0447.json`) improved silhouette overlap for most actions in
earlier experiments, but regressed idle and is not validated. See
[research/findings.md](research/findings.md). To try it:

```sh
python -m spritemotion fit ... --camera games/ultima-online/profiles/cameras/character-depth-0447.json
```

## Region-mask experiment

The imported garment-region masks, packaging tools and bone/depth handoff are documented in [region-masks/README.md](region-masks/README.md). Local frames and the fitted Blender scene are under workspace/ultima-online/region-audit/.
