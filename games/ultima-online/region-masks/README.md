# Body 400 region-mask experiment

Imported from UltimaOnlineWorldWar's `output/uo-human-audit/all-actions-region-pass` on 2026-09-25. This is the continuation location for the experiment. Originals were copied, not moved.

Canonical scripts live here; game-derived assets remain in the ignored `workspace/ultima-online/region-audit/` directory:

- `all-actions-region-pass/`: source frames, masks, comparisons, depth results and unpacked package.
- `poses/UOCharacter2_AllActions_Pass2.blend`: fitted poses for all 35 actions.
- `reference/`: original action index, current-stage snapshot, second-pass review and `SUPERSEDED-uo-body400-region-masks.rar` (old axis-line version; not final).
- `migration-manifest.json`: source-to-copy SHA-256 verification.

The historical current-stage snapshot may reference earlier experiments that were not imported. The copied Blender scene has not been checked for external resource dependencies.

## Running

Use Python with NumPy, SciPy and Pillow installed. From the repository root:

```powershell
$env:SPRITEMOTION_UO_SOURCE = '<your UO client folder>'
python games/ultima-online/region-masks/build_regions.py
python games/ultima-online/region-masks/package_masks.py
```

`SPRITEMOTION_REGION_WORKSPACE` optionally overrides the data directory. Packaging uses the copied `../reference/anim_400_index.json`. The standalone classic MUL reader `uo.py` was imported from BodyMaskLab to preserve garment decoding behavior. It does not replace SpriteMotion's extraction adapter.

`depth_test.py` additionally requires PyTorch, Transformers, model downloads/cache and a CUDA GPU. Existing depth results were copied; rerunning depth is optional.

## Handoff status

The handoff reports approved region masks, anchors, cell layout and bounding boxes. That approval does not establish anatomical ground truth or approve the bones. Joint-to-joint bones fail where limbs overlap the torso or merged legs pair incorrectly. Grey lines estimate one endpoint and are least reliable. Earlier principal-axis bones could run sideways through wide shapes.

Depth Anything V2 Small produced rough near/far; cached MiDaS produced a blob. Neither resolved overlapping limbs. Next experiment: project joints and depth ordering from the fitted Blender poses, validate against sprites, then consider brightness as an unverified cue. Reported pose overlap of 61–66% is not independently verified here.

The source release README was empty and the unpacked README missing. A replacement records these limitations. Copied historical scripts beside the data are snapshots; run the canonical scripts in this directory. No final archive has been rebuilt.

## Astra armature pass

`fit_armature.py` fits a connected 20-point 2D skeleton using the latest masks and the existing pose estimates as identity/length priors. It assigns visible region pixels exclusively to A or B, leaves ambiguous pixels unassigned, constrains joint motion and bone lengths, and uses a weak previous-frame displacement prior. Shoulders and hips stay connected to core joints instead of treating garment contacts as anatomical endpoints. Hollow points/dashed lines show missing or weak mask support. The confidence numbers are heuristic, not calibrated accuracy probabilities.

The selected output contains 1,680 poses (33,600 joints): new fits for 34 actions and preserved manual references for action 22. The action-22 fitted candidate regressed against the six approved SE poses: mean joint error 1.01 to 2.46 px. Its candidate is retained separately; the main result preserves the existing manual fall references and exactly includes the six approved corrections. No original annotations, mask pixels or Blender scenes are modified.

```powershell
python games/ultima-online/region-masks/fit_armature.py
python games/ultima-online/region-masks/review_armature.py
python -m unittest discover -s games/ultima-online/region-masks -p test_armature.py
```

Use `--actions 0 9 16 22` on the fitter for a pilot; run the full fitter before building the complete review. Dependencies: NumPy, SciPy, Pillow. In this workspace SciPy was installed locally in `workspace/python-deps`; set `PYTHONPATH` to that directory when using the bundled Python runtime.

Results are in `workspace/ultima-online/region-audit/armature-pass-astra/`:

- `index.html`: self-contained local viewer, 35 actions, eight views, playback, joint labels and mask opacity; stable action bounds retain motion/anchor placement.
- `comparison.png`: latest masks, previous boundary bones, new armature on masks and new armature on sprite.
- `sheets/`: all stored frames by action with distinct cyan/magenta arms, green/orange legs, yellow head/neck, lavender torso/pelvis and square white-outlined hands.
- `poses/`: selected pose JSON; `candidates/action-022.json`: rejected fall-fit candidate.
- `report.json`: candidate mask-fit diagnostics and source hashes; `validation.json`: coverage, coordinates, mirroring and the fall regression check.

The distance-to-mask metric is optimized by construction and is not anatomical accuracy. A/B labels are inherited, not independently recovered; occlusion and true depth remain unsolved. The existing Blender poses were not refitted or modified by this 2D pass.
