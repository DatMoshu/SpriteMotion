# Annotation format

Annotations are 2D joint positions on sprite frames. They are the part of
SpriteMotion that people build together, so the format records where each
pose came from and which pixels it was drawn on.

Schemas are in `common/schemas/`:

| File | Schema id | Describes |
|---|---|---|
| `dataset.json` | `spritemotion.dataset` ([schema](../common/schemas/sprite-sequence.schema.json)) | one extracted character: canvas, directions, camera, frames with fingerprints |
| `skeleton.json` | `spritemotion.skeleton` ([schema](../common/schemas/skeleton.schema.json)) | joint names, drawing chains, symmetric pairs |
| `annotations/<layer>/<sequence>.json` | `spritemotion.pose-annotations` ([schema](../common/schemas/pose-annotations.schema.json)) | poses of one sequence in one layer |
| `games/<game>/game.json` | `spritemotion.game` ([schema](../common/schemas/game.schema.json)) | a game adapter and its characters |

All coordinates are **canvas pixels**: origin at the top left, x to the right,
y down. The canvas has a fixed size per dataset and the character's ground
origin at `canvas.anchor`, so poses from different frames and directions share
one coordinate system.

## Frame identity and fingerprints

Every extracted frame has:

- `frame_id`: `<dataset_id>/<sequence>/d<direction>/f<frame, 2 digits>`,
  for example `ultima-online/body-400/action-022/d3/f05`.
- `fingerprint`: `sha256:` followed by the SHA-256 of the frame's normalized
  RGBA canvas. For UO this is the unhued canvas after placement and, for
  client-mirrored views, after mirroring.

Every pose stores the `frame_id` and the `source_fingerprint` of the frame it
was drawn on. When a bundle is applied to a dataset
(`spritemotion extract` or `apply-annotations`), each pose is classified as:

| Result | Meaning | What happens |
|---|---|---|
| matched | same `frame_id`, same fingerprint, joints valid for the skeleton and canvas | applied |
| mismatched | the frame exists but its pixels differ, for example another client version or a patched sprite | **not applied**, listed in the report |
| unknown_frame | the dataset has no such direction or frame | not applied, listed |
| invalid | wrong `frame_id`, unknown joint, or coordinates off the canvas | not applied, listed |

The report is written to `<dataset>/annotations/apply-report.json` and
summarised by `spritemotion status`. `apply-annotations --strict` exits
non-zero on any mismatch. Nothing is guessed or moved to "fix" a mismatch.
Redraw those poses in the editor.

`spritemotion fit` checks fingerprints again and skips mismatched poses. Its
solution file records them under `target_selection.skipped_mismatch`.

## Two layers

```text
<dataset>/annotations/estimates/<sequence>.json     estimate layer
<dataset>/annotations/corrections/<sequence>.json   correction layer
```

- **Estimates** are automatic starting points: mirrored partners, rig
  projections, image-based estimators, or legacy manual sets that were
  imported. Tools add to this layer. The editor never writes to it.
- **Corrections** hold only the poses a person *meaningfully* touched: moved
  joints, set a review status, or wrote notes. Untouched estimates are never
  copied into this layer.
- **Effective pose** = the correction if there is one, otherwise the estimate.

Bundles in the repository (`games/<game>/annotations/<character>/`) use the
same two folders. Applying a bundle never overwrites existing local
corrections unless you pass `--overwrite-corrections`, and a `.bak` is kept
when you do.

## A pose

```json
{
  "frame_id": "ultima-online/body-400/action-022/d3/f02",
  "direction": 3,
  "frame": 2,
  "source_fingerprint": "sha256:…",
  "provenance": {"method": "manual", "independent": true},
  "review": {"status": "approved", "notes": "left forearm hidden behind torso", "updated_at": "…"},
  "joints": {
    "head":  {"x": 131.5, "y": 118.0, "confidence": 1.0, "visibility": "visible", "status": "corrected"},
    "neck":  {"x": 129.0, "y": 127.5}
  }
}
```

### Provenance

| `method` | Made by | `independent` |
|---|---|---|
| `manual` | a person placing joints on the sprite | `true` |
| `estimator` | an image-based estimator reading the sprite | `true` |
| `mirrored` | copy of the partner view, x → 2·`mirror_axis_x` − x | inherits from the source; `source_method` and `mirrored_from` are recorded |
| `rig_projection` | joints of a 3D rig projected through the camera | **`false`** |
| `interpolated` | between neighbouring frames | usually `false` |
| `imported` | another tool's data whose origin is unknown | as declared |

`independent` means the joints were read from the sprite itself. **A rig
projection is not evidence about the sprite.** If you fit a rig to its own
projections, the fit simply reproduces that rig. So `fit` refuses targets that
are neither independent nor approved unless you pass
`--allow-dependent-targets`, and it lists refused poses under
`target_selection.skipped_dependent`. The editor shows the provenance of every
pose, for example "Estimate · Rig projection — not independent evidence".

A correction the editor saves gets `method: "manual"`, and `source_method`
records the estimate it started from. It is marked `independent: true` only
when it is approved, or when that estimate was already independent. Moving a
few joints of a rig projection does not turn the rest of it into observation.

### Review

`review.status` is `unreviewed`, `in_progress`, `approved` or `rejected`.
Approve a pose only after checking every joint. Moving a joint in the editor
resets the status to `in_progress`. Fitting in the default `approved` mode
uses only approved poses, and weights every joint of an approved pose as
fully confident.

### Joints

| Field | Meaning |
|---|---|
| `x`, `y` | canvas pixels (required) |
| `confidence` | 0–1; used as the fit weight for joints of unapproved poses |
| `visibility` | `visible` (weight 1), `unknown` (0.7), `occluded` (0.3), `outside` (0: ignored) |
| `status` | `estimate`, `corrected`, or `mirrored_correction` |

A missing joint is simply absent from `joints`.

## Skeletons and limb identity

A skeleton lists the joint names, the chains the editor draws (with colours),
connections drawn dashed because they are inferred, and `symmetric_pairs`.

Sprites often do not show which limb is anatomically left or right. A 20-joint
skeleton can therefore use neutral chain names (`arm_A_*`, `arm_B_*`) instead
of `left`/`right`. The annotation file's `limb_identity` states how A and B
relate to anatomical sides for that set. A rig mapping says which rig side
each chain drives (`"sides": {"A": "L", "B": "R"}`). The fitter's
`--swap-sides` option tries the other assignment.

**Mirroring keeps joint names by default.** When a view is produced by
flipping its partner, the flipped pose keeps the same chain labels. It does
not swap to screen left and screen right, because the pixels are the same
limbs, mirrored.

## Estimates are generated, corrections are shared

`estimate-mirror` and `estimate-rig` only add estimates where a pose is
missing, and they never touch corrections. `promote` copies the corrections
you reviewed from a workspace dataset into a repository bundle. It refuses a
whole sequence if any of its corrections fails to match your extracted frames,
and it keeps a `.bak` of the bundle file it replaces. Because promote replaces
the bundle's correction file for that sequence, the pull-request diff is where
changes to poses that were already approved get reviewed. See
[CONTRIBUTING.md](../CONTRIBUTING.md).
