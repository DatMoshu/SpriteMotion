# UO_Model3D v13

UO_Model3D v13 by Levy, shared with the artist's permission.

A rigged 3D rebuild of the Ultima Online male body (body 0x190) with its fitting pipeline. SpriteMotion uses it as the
canonical body (rig `UO_Rig`, 54 bones since the 2026-10-09 update). Start with `README_EN.md` (English) or
`README.md` (Polish).

## What is here

Upstream commit: https://github.com/Kserian/UO_Model3D at `e9544f6` (2026-10-09; the previous copy was `3eaae69`).
`model/` (the `.blend` and the albedo PNGs), `pipeline/` (scripts, `cloak_pitch.json`, `weapon_motion.json`), `vdtool/`,
and the two READMEs. The `.blend` is stored with git LFS (`git lfs pull` after cloning). Upstream publishes no `.fbx`
or `.glb` and SpriteMotion reads none, so none is shipped.

Not copied (not needed to build or fit): upstream `docs/` (Polish hand-over notes and QA measurements, some with
previews made against original frames) and `CLAUDE.md` (Levy's own agent instructions).

## What is deliberately not here

Everything extracted from the Ultima Online client is EA data and is not published:

- `client/` (original body and horse frames, extraction output; 1,360 PNGs upstream).
- All `.vd` files (`body400.vd`, `horse200.vd`, `pipeline/body13/mul/`, the example shirt layer), the original-frame atlas
  (`UO_Original_Atlas.png`, `uo_original_frames.json`), the shirt preview over an original, and `pipeline/test_data/`.
- All `*.npz` and `*.pkl` caches (fit targets from original silhouettes, and unsafe to load from a stranger).
- The packed original-frame atlas inside the `.blend` (image `UO_Original_Atlas`, text `uo_original_frames.json`):
  `model/UO_Body_0x190.blend` is the stripped copy (`pipeline/strip_originals.py`, `uo_exact` = 0). The embedded scripts
  (`render_uo_layer.py`, `cloth_lib.py`, `uo_bind_item.py`, ...) are Levy's, unchanged.

The READMEs still describe those files and the "exact modes" that need them. To use them, supply your own client:
copy your `anim1_0x0190.vd` to `pipeline/body400.vd`, then run `build_originals.py` and `pack_originals.py` as the
README says. The scripts that rebuild them stay in `pipeline/`.

## License

Shared with permission of the artist (Levy). `pipeline/body13/mh/` holds MakeHuman base data, which the MakeHuman
project publishes under CC0.
