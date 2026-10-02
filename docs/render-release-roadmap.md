# Reliable UO renders and public releases

Status: 2026-10-02. The code repository is public at
[DatMoshu/SpriteMotion](https://github.com/DatMoshu/SpriteMotion). Public source availability is not a claim that
every outfit, animation and client combination is production-ready.

## What works now

- Fit history, autosave and three recoverable disk versions.
- Pack, slot, named-group and item corrections, filtered by animation, direction, or both. Mirrored facings share
  the corresponding stored direction. Corrections reach both the lab and fit-aware Blender builds.
- Torso-aware back-attachment masking and separate clothing masking. Original-sprite previews now apply depth masks.
- Lab buttons to build an item and rebuild only its changed existing blocks into a new validated revision.
  Untouched VD blocks stay byte-identical; the original job remains available.
- Partial rebuilds reject changes to the model, renderer, source meshes or palette; a fresh build is required.
- The October 2026 model/renderer update is supported, including its 112-bone base rig and native 256×256 canvas.

Local acceptance evidence includes 125-frame backpack masking comparisons (five representative actions, five
stored directions), a skinned chest build exercising combined correction scopes, and a partial rebuild proving
an unaffected block remained byte-identical. These are targeted checks, not full equipment coverage or in-game proof.

## Render acceptance gates, in order

| Gate | Work | Exit evidence |
|---|---|---|
| 1. Make final renders authoritative | Compare the new renderer's worn-part rules, original-outline correction, torso mask, push-out and mounted holdout against the live lab. Use the rendered review for export decisions. | Reproducible side-by-side cases for front/back/side views; no unexplained mask disagreement. Preview differences are either fixed or clearly labelled. |
| 2. Cover equipment and every animation | Test at least three representative items per slot, all 35 actions, five stored directions plus three mirrored views. Include large weapons, shields, cloaks, skirts, hair, falls and mounted poses. | Correct block/frame IDs; fixed 256×256 canvas and (128,192) anchor; no unexplained clipping or empty frames; visual review of crossings and silhouettes. |
| 3. Fix exceptions locally | Apply action/direction/item/group corrections where base fitting fails. Improve twist/finger/weapon/cloth targets where a transform cannot fix deformation. | A/B images improve the failing poses; regression checks show unrelated actions/items remain unchanged. Head stabilization stays experimental until original-sprite matching supports it. |
| 4. Validate a complete outfit | Render combined outfit layers and exercise body hiding, straps, back items, weapons, paired pieces and garment intersections together. | No double hiding, missing limbs, front/back swaps or unexpected layer ordering across the full action set. |
| 5. Prove client compatibility | Validate full VD output, stage classic-client imports on copies, handle animation/static IDs and body/equipment conversions, then equip in the target client/server. | In-game screenshots/video of walking, combat, casting, death, mounting and turning. Confirm intended body/sex support. This gate is not complete until an actual client test passes. |

Pure depth masking cannot correct a misaligned rig or an item that needs a different silhouette. Likewise, a lower
poke count is not proof of better UO artwork. Keep numerical validation and visual acceptance separate.

## Public-release path

1. **Developer preview:** publish reviewed code and documentation; keep the current status and unsupported cases
   visible. Bundle only redistributable procedural examples. Game data, canonical scenes, commercial pack files,
   mappings and generated art remain local. The sidecar is never pushed.
2. **Reproducible setup:** test a clean checkout, document supported Python/Blender versions, make missing local
   prerequisites actionable, and verify the sample workflow without developer-specific paths. Document upstream
   tool/model provenance and permitted installation separately from the repository's MIT code license.
3. **Automated release checks:** run unit/schema tests, browser/build fit-parity checks, save/recovery tests and
   public-file scanning in CI. Add a procedural Blender regression scene so masking and selective rebuild checks
   can run without distributing UO or commercial assets.
4. **Alpha release:** tag a release with setup instructions, a tested compatibility matrix, known limitations and
   permitted screenshots/examples. Have an outside tester complete installation and a sample export.
5. **Beta release:** finish gates 1–5 above on the supported client/body combinations. Require full-action regressions,
   recoverable saves, reproducible bug reports and successful in-game outfit tests before advertising reliable UO
   equipment production.

The next highest-value work is a full-action, three-items-per-slot acceptance matrix on the updated renderer,
followed by one complete outfit imported into the actual target client. More preview controls are lower priority
than those two proofs.
