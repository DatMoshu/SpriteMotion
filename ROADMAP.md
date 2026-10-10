# Roadmap: toward UO parity

SpriteMotion's goal is equipment that looks and moves like original Ultima Online art: every action, every facing,
correct layering, and a working import into a classic client. This page is the public, contributor-facing view of
where that stands. The detailed acceptance plan is [docs/render-release-roadmap.md](docs/render-release-roadmap.md);
the maintainer's running notes are in [docs/handoff.md](docs/handoff.md).

Status legend: **done** (verified locally with evidence), **partial** (works on targeted cases, not full coverage),
**open** (not started or not yet proven). Help is welcome on anything marked partial or open.

## What already works

- **Fit Lab editing**: undo/redo with a 100-step history, autosave, browser crash recovery and three recoverable disk
  saves. See [tools/fit-lab/README.md](tools/fit-lab/README.md).
- **Scoped corrections**: pack, slot, named-group and item corrections, optionally per action and/or direction.
  Mirrored facings share their stored direction. The lab and Blender builds resolve them with the same rules.
- **Body masking**: torso-aware back-attachment masking, separate clothing masking and per-part body hiding under
  clothes. See [docs/body-occlusion.md](docs/body-occlusion.md).
- **Builds from the lab**: build an item, then rebuild only its changed blocks into a new validated revision.
  Untouched VD blocks stay byte-identical; mixed-version rebuilds are refused.
- **Current model**: the October 2026 UO_Model3D update (112-bone rig, native 256x256 canvas, anchor (128,192)).
- **CC0 starter equipment** for all 25 UO layer routes: [examples/cc0-starter](examples/cc0-starter/README.md).

## Render acceptance gates

| Gate | Status | What is left | Where help is wanted |
|---|---|---|---|
| 1. Final renders are authoritative | partial | Side-by-side cases showing the Blender renderer and the live lab agree on worn-part rules, outline correction, torso mask, push-out and mounted holdout. | Reproducible front/back/side comparisons; labelling preview-only differences. |
| 2. Every animation, every slot | open | At least three representative items per slot across all 35 actions, five stored directions plus three mirrored views, including large weapons, shields, cloaks, skirts, hair, falls and mounted poses. | Running and reviewing the acceptance matrix; filing [parity gaps](https://github.com/DatMoshu/SpriteMotion/issues/new?template=parity_gap.yml). |
| 3. Fix exceptions locally | partial | Action/direction/item/group corrections exist; twist, finger, shield and cloak/skirt chain targets (`proposed_target` in mappings) are not yet used by `pack_fit.py`. | Rig targets for twist bones, fingers and cloth chains; A/B evidence on failing poses. |
| 4. A complete outfit | open | Combined outfit layers with body hiding, straps, back items, weapons, paired pieces and garment intersections across the full action set. | Building and reviewing one full outfit; reporting layer-order or double-hiding issues. |
| 5. Client compatibility | open | Full VD output staged into a copy of a classic client, animation/static IDs and body/equipment conversions handled, then equipped in-game. | In-game tests on your own client/server; documenting Body.def / Bodyconv.def / Equipconv.def routing. |

## Known open items

- Not yet verified: a full 35-action lab build, a rebuild whose base slot fit changed, mounted actions, cloaks
  (torso mask), and weapons on the new weapon bones.
- The lab's poke-through metric models the renderer's 1 cm holdout margin, its push-out (reported as an upper
  bound) and the occlusion modes. It is still a measure on the lab's 3D body, so compare numbers between fits.
- Untested outfit-lab options: `merge_items.py`, `make_gump_cloak.py`, `build_item.py --planar/--cut`,
  `atlas_to_vd.py --body/--outline`.
- Release path: reproducible clean-checkout setup, a procedural Blender regression scene for CI, then an alpha
  release with a tested compatibility matrix. See the
  [public-release path](docs/render-release-roadmap.md#public-release-path).

## How to help

- Read [CONTRIBUTING.md](CONTRIBUTING.md) first: never commit game data, extracted frames, commercial pack files or
  machine paths.
- Use the [wiki](https://github.com/DatMoshu/SpriteMotion/wiki) for setup walkthroughs and the
  [Discussions](https://github.com/DatMoshu/SpriteMotion/discussions) board for questions and ideas.
- Report a mismatch with original art using the **Parity gap** issue template: action id, direction, slot, item,
  expected versus actual, and a screenshot of SpriteMotion output only (never original client art).
