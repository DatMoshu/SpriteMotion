# UO_Model3D v13

UO_Model3D v13 by Levy, shared with the artist's permission.

A rigged 3D rebuild of the Ultima Online male body (body 0x190) with its fitting pipeline. SpriteMotion uses it as the
canonical body (rig `UO_Rig`, 112 bones after the 2026-10 weapon-bone update). Start with `README_EN.md` (English) or
`README.md` (Polish).

## What is here

`model/` (`.blend`, `.fbx`, `.glb`, albedo PNGs), `pipeline/`, `vdtool/`, and the two READMEs. The three model files are
stored with git LFS (`git lfs pull` after cloning).

## What is deliberately not here

Everything extracted from the Ultima Online client is EA data and is not published:

- `client/` (original body and horse frames, extraction output).
- All `.vd` files (`body400.vd`, `horse200.vd`, `pipeline/body13/mul/`, the example shirt layer), the original-frame atlas
  (`UO_Original_Atlas.png`, `uo_original_frames.json`), the compare GIFs and shirt preview, and fit targets built from
  original silhouettes (`views_*.npz`, `horse.npz`).
- All `*.pkl` result caches (also unsafe to load from a stranger).
- The packed original-frame atlas inside the `.blend`: `model/UO_Body_0x190.blend` is the stripped copy.

The READMEs still describe those files and the "exact modes" that need them. To use them, supply your own client:
copy your `anim1_0x0190.vd` to `pipeline/body400.vd`, then run `build_originals.py` and `pack_originals.py` as the
README says. The scripts that rebuild them stay in `pipeline/`.

## License

Shared with permission of the artist (Levy). `pipeline/body13/mh/` holds MakeHuman base data, which the MakeHuman
project publishes under CC0.
