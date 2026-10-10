# UO slot masking data: region masks, equipment layers and the armature pass

"Slot masking data" is the data that says **which part of the body each equipment slot covers**. It has three pieces, all
in the repository, built at different times for different consumers:

1. **Body 400 region masks** (`games/ultima-online/region-masks/`): for every frame of the classic male body, a
   per-pixel label (head, neck, torso, ...) derived from real UO garments.
2. **Equipment slot data** (`games/ultima-online/equipment/layers.json`): the 25 client layers, with the rig bones and
   region names each one covers.
3. **The Astra armature pass** (`fit_armature.py`, `review_armature.py`): an experimental 2D skeleton fitted to those
   masks.

This is not the render holdout. How the Blender renderer cuts items where the body is in front is a different system,
covered in [Body holdout and Hide body](masking-cleanup.md). Section 5 explains how the two relate (they barely touch
today).

Everything here is run from a worktree whose `workspace/` holds a copy of the region data; see "What was run" at the end.

**Client data warning.** The masks, frames, comparison sheets and review pages are derived from `anim.mul`. They live
in the ignored `workspace/` and must never be committed, posted or put in a PR. This guide has no images of them.

## 1. Body 400 region masks

### What a mask is

A mask is a 256x256 PNG of region ids, one per frame: `a<action>_d<facing>_f<frame>_region_ids.png`, next to the
`_clothed.png` (dressed reference) and `_body.png` (the bare body) of the same frame. The canvas and anchor are the
UO canvas: 256 px, ground contact at (128, 192). 35 actions, 5 stored facings (SE, S, SW, W, NW; N, NE and E are
mirrors of W, SW and S), 1,050 frames in all.

| id | region | where the label comes from |
|---|---|---|
| 1 | head | plate helm, anim 563 (mask only) |
| 2 | neck | leather gorget, anim 546 (mask only) |
| 3 | torso | shirt, anim 434 |
| 4 | upper_arms | leather sleeves, anim 544 minus the glove cuff (mask only) |
| 5 | hands | bare skin out of the sleeve, plus glove (anim 545) past the sleeve (mask only) |
| 6 | thighs | long pants, anim 431, between the tunic hem and the knee-boot top |
| 7 | feet | bare skin below the pants |
| 8 | shins | knee boots, anim 477, over the pants (mask only) |
| 9 | forearms | glove cuff over the sleeve (mask only) |
| 10 | hips | tunic, anim 909, minus the shirt, over the pants (mask only) |
| 255 | unknown | pixel no rule could label (drawn red) |

"Mask only" means the garment's shape is used to label pixels but the garment is never drawn. Body pixels that no
garment covers inherit the nearest labelled pixel. The idea is simple and honest: the original artists drew real
clothes on the real body, so where a garment's silhouette lies, that region of the body lies underneath.

### How they are built

```powershell
$env:SPRITEMOTION_UO_SOURCE = '<your UO client folder>'
python games/ultima-online/region-masks/build_regions.py          # all 35 actions, or: ... build_regions.py 0 9 16
python games/ultima-online/region-masks/package_masks.py          # release folder
```

- `build_regions.py` reads the client through `uo.py` (a read-only classic MUL reader), labels each frame with
  `frame_regions`, writes `frames/` and `compare/regions-actionNN.png` under the data folder and a
  `region-report.json`. The data folder is `workspace/ultima-online/region-audit/all-actions-region-pass`, or
  `SPRITEMOTION_REGION_WORKSPACE` if set.
- Careful: the report is rewritten by every run, so a run for a few actions leaves a report for only those actions.
  `package_masks.py` needs the report for all 35, so run `build_regions.py` without arguments before packaging.
- `package_masks.py` writes `uo-body400-region-masks/`: per-action compare sheets, mask-only sprite sheets with
  a JSON sidecar, "gizmo" sheets (anchor, cell, bounding box, region axes, joint candidates) and `manifest.json` with
  `checksums.json`. It also needs `reference/anim_400_index.json` (the action index) in the sibling `reference/`
  folder of the data folder. Joint candidates are boundaries between regions (`neck_base` = neck/torso, `shoulder` =
  torso/upper_arms, `knee` = thighs/shins, ...); the manifest says they are garment edges, not claimed bones, and
  that paired limbs are not split left/right.

### Status

- **Approved** (by the handoff): the comparison-sheet masks, anchor, cell layout and bounding boxes. That is an
  approval of layout, not of anatomy.
- **Estimates, not ground truth.** The manifest status is "Estimated from garment silhouettes; not manually reviewed
  anatomy". Garment edges (a cuff, a hem) are not joints: `elbow_approx` is the top of the glove cuff and sits near the
  wrist when the arm is straight; `skirt_hem` and `waist` are garment edges.
- Quality numbers from the run in this guide (`region-report.json`): 35 actions, 1,050 frames, no garment/body
  sequence-length mismatch, 51 unknown pixels in total, every action at least 88.9% seeded directly by a garment (the rest
  by nearest-label fill).
- **Body 400 only.** Body 401 (female) and other species have no region masks; the outfit lab says so.
- The old principal-axis "bones" and the `SUPERSEDED-...rar` release are obsolete. No final archive has been rebuilt.

### Known failures

From the handoff, still true: joint-to-joint bones fail where limbs overlap the torso or merged legs pair incorrectly;
grey lines have one estimated endpoint and are least reliable; earlier principal-axis bones could run sideways through
wide shapes. Monocular depth does not fix it (below).

`depth_test.py` (needs PyTorch, Transformers, model downloads and a CUDA GPU) runs two monocular depth models on six
frames and prints the mean "nearness" (1 = nearest) per region. It was rerun for this guide and gives the same verdict
as the handoff: the MiDaS-hybrid output is a
blob (head, neck, torso and upper arms all 0.8-0.97 on action 0 SW, i.e. no depth ordering between them). Depth
Anything V2 Small is only rough near/far. Neither resolves overlapping limbs.

## 2. Who reads the masks

Only the **2D outfit lab** (`games/ultima-online/outfit-lab/`), which works on original UO frames:

- `build.py` and `build_item.py` read `frames/a<NN>_d<facing>_f<NN>_region_ids.png` (`--masks` overrides the folder).
- A garment's `hide` list is region ids to cut out of the *new* cloth, for example `{'robe': [1, 5], 'shirt': [1, 5]}`:
  a robe or shirt design must not cover the face (1) or the hands (5). `build_item.py --hide-labels 1 5` does the same
  for one item. This is the practical meaning of "slot masking" in the 2D pipeline.
- The atlas it writes has a coloured-mask row, and `verify.py` checks the result.

`clothing_fit.py` is a benchmark rather than a pipeline step: it dresses a candidate body replacement in every original
garment and uses the region masks to define the "exposure contract" (a region counts as covered when most of its pixels
sit under the garment), then counts skin that pokes out.

The Blender pipeline (Fit Lab, `tools/uo-content`) does **not** read these PNG masks.

## 3. The equipment slot data

`games/ultima-online/equipment/layers.json` is a `spritemotion.equipment-slots` document (schema in
`common/schemas/equipment-slots.schema.json`). It lists the client's 25 equipment layers. For each: id, name, `kind`
(`held`, `worn`, `jewelry`, `body`, `container`, `internal`), whether it has per-action body animations (`animated`),
the Fit Lab template (`studio_part`), the canonical rig bones the item is fitted to (`rig_bones`) and the region names
it covers (`regions`).

```text
Layer 5  Shirt        studio_part chest   bones spine chest upper_arm.L/R        regions torso, upper_arms
Layer 3  Shoes        studio_part boots   bones foot.L foot.R                    regions feet
Layer 8  Ring         (not animated)                                             regions (none)
```

The ten region names (`head neck torso upper_arms forearms hands hips thighs shins feet`) are the same ten labels as
the masks above, so one vocabulary is shared. The reading side is narrower than the data:

- **Used:** asset-pack mappings pick a layer, and through it the `studio_part` (the Fit Lab template and which fit
  rule applies) and `rig_bones` (what the pack's part is fitted to). Tests in `tests/unit/test_asset_packs.py` and
  `test_starter_assets.py` read the file; `common/pipeline/status.py` validates it.
- **Not used by any code today:** the `regions` field. Nothing in `tools/` or `common/` reads `regions` from
  `layers.json`. It is documentation of intent, and a possible bridge from layers to the 2D masks.
- Jewelry layers (ring, talisman, bracelet, earrings) and Mount are not animated and have no regions or template.
  Layer 20 is shared between cloaks and quivers, and layers 1/2 between shields and two-handed weapons.

## 4. The Astra armature pass (experimental)

`fit_armature.py` fits a connected 20-joint 2D skeleton (`skeletons/humanoid-20.json`) to the masks, starting from
the existing pose estimates in `annotations/body-400/estimates/`. Pixels are assigned exclusively to limb A or B,
ambiguous ones are left unassigned, joint motion and bone lengths are constrained, and a weak previous-frame prior
smooths the motion. It never writes to the source annotations.

```powershell
python games/ultima-online/region-masks/fit_armature.py                  # all 35 actions
python games/ultima-online/region-masks/fit_armature.py --actions 0 9 16 22   # pilot
python games/ultima-online/region-masks/review_armature.py               # review page, comparison board, validation.json
python -m unittest discover -s games/ultima-online/region-masks -p test_armature.py
```

Output goes to `workspace/ultima-online/region-audit/armature-pass-astra/` (it writes under the repository checkout it
runs from, so a worktree has its own copy): `poses/` (1,680 poses = 33,600 joints), `sheets/`, `candidates/`, `report.json`,
`validation.json`, `comparison.png` and a self-contained `index.html` viewer.

What to trust:

- The distance-to-mask number (for example 1.51 to 0.20 px on action 0) is what the optimiser minimises. It is **not**
  anatomical accuracy. A/B labels are inherited from the priors, not recovered, and there is no true depth or occlusion.
- The only independent check is the six approved SE poses of action 22 (fall). The fitted candidate was **worse**
  than the prior there (mean joint error 1.01 px to 2.46 px over 120 joints), so it was rejected: the selected output
  for action 22 keeps the manual references and contains the six approved poses exactly. The candidate stays in
  `candidates/`.
- Status of the whole pass: unreviewed, not approved. Hollow points and dashed lines in the viewer mark joints with
  weak or no mask support.

## 5. How this connects to the Fit Lab and the renderer today

| System | Data | Used for | Reads the PNG masks? |
|---|---|---|---|
| 2D outfit lab (`outfit-lab/`) | region ids per pixel | cut face and hands out of new cloth; atlas rows | yes |
| Blender renderer holdout (`tools/uo-content/occlusion.py`) | the posed 3D body, per-triangle region of the 3D mesh | cut item pixels where the body is in front | no |
| Fit Lab Hide body | faces of the 3D fitting body | stop skin push-out under clothes | no |
| `layers.json` | layer to bones/template/regions | pick the fit template and rig bones for a pack part | no (`regions` unread) |

`occlusion.py` has its own `triangle_regions`: region names there are labels on **3D mesh triangles** (so "left and
right kept apart" is possible), not the 2D UO masks. The two vocabularies look alike but are separate data. See
[Body holdout and Hide body](masking-cleanup.md) for the 3D side.

Gaps worth knowing: nothing validates that a layer's `regions` agree with what the original garments actually cover (the
masks could test that); and the 3D body regions are not derived from the 2D masks.

## 6. What is next

From the handoff and the status above, not yet started in the repo:

1. Project joints and depth ordering from the fitted Blender poses (`UOCharacter2_AllActions_Pass2.blend`, 35 actions),
   validate against the sprites, then consider brightness as an unverified cue.
2. Broaden the independent check beyond six action-22 poses before calling any armature result approved.
3. Body 401 and other bodies need their own masks.
4. Decide whether `layers.json` `regions` should be tested against the masks or dropped.

## What was run, and what was not

Run for this guide (Windows, Python 3.12.5 environment with NumPy 1.26, SciPy 1.11, Pillow 12.3; client folder read only,
`SPRITEMOTION_UO_SOURCE` set; data copied into the worktree's own `workspace/`, nothing outside it written):

- `build_regions.py 0 9`, then `build_regions.py` (all 35 actions): exit 0, 1,050 frames, 51 unknown pixels in total.
- `package_masks.py`: exit 0, 35 actions, 1,050 frames (after copying `reference/anim_400_index.json`; without it the
  script stops with `FileNotFoundError`).
- `fit_armature.py --actions 0 9 16 22` and then the full `fit_armature.py`: exit 0.
- `review_armature.py`: exit 0; holdout figures quoted in section 4 come from its `validation.json`.
- `python -m unittest ... test_armature.py`: 3 tests OK.
- `depth_test.py`: exit 0 on a CUDA machine (torch 2.6.0+cu124), models loaded from the Hugging Face cache or download.
- Outfit-lab consumer: `build_item.py --graphic 0x1517 --design <synthetic two-colour image> --actions 0` built the shirt atlas
  (animation 434, layer 5, 0 missing); `python -m unittest discover -s games/ultima-online/outfit-lab -p test_fitting.py`: 6 tests OK.

Not verified:

- `build.py` for the full ten-item outfit lab, `verify.py`, and the browser viewers (`index.html` from `review_armature.py`,
  `armature_review.html`, the pose editor server): not opened or run.
- `review_female_motion.py`, `prepare_female_motion.py` and `clothing_fit.py`: not run (they need body 401 or a candidate
  body).
- The regenerated masks were not compared pixel for pixel against the older copy in the main checkout; only the report
  numbers above were read.
- Anything about the Blender poses (`poses/*.blend`): not opened.
