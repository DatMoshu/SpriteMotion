# Body occlusion in final equipment renders

The complete posed body hides equipment behind it without appearing in the exported equipment image.
`tools/uo-content/occlusion.py` supplies the final Blender depth holdout through `fit_runtime.py`.
It does not modify the separately installed upstream renderer.

The old clothing policy excluded the torso and globally exempted every anatomical part worn by any item.
It also discarded left/right suffixes. Paired bracers could consequently show through a torso or the opposite arm.

## Geometry and contact

The renderer now keeps a pristine body proxy with the body's animation modifiers. It is never rendered as color.
The proxy remains complete when the fitting mesh has faces removed by Hide body under clothes. Push-out continues
to use the fitting mesh and its existing collision regions; changing visibility does not change that solver.

For every pixel, compare nearest body depth with nearest item depth. Body closer by more than the normal holdout
margin removes the item pixel. Clothing mode can extend that margin to the saved hide-body inward distance only
when the nearest body and item surfaces belong to the same anatomical region. Left and right remain distinct;
twist groups normalize to their limb while preserving the side. This is a finite penetration tolerance, not an
unlimited exemption. A far-side surface on the same limb still disappears when it exceeds the tolerance.

Body mode has no garment-specific allowance. None bypasses body masking. The upstream original-sprite outline
correction and mounted horse masking remain in place. The final mask follows the original body's silhouette;
the model supplies front/back depth, so inaccurate source geometry can still require fit corrections.

## Recovery and validation

No saved adjustment format changes. New renders use the new policy. Renderer fingerprints include the occlusion
module, so old builds cannot be selectively mixed with new masking; create a fresh build. Old jobs remain available.
The lab's live geometry preview is still approximate and is not changed by this renderer patch.

Regression coverage includes torso blocking, opposite limbs, small own-surface penetration, deep own-surface
occlusion, a rear garment trying to exempt a different front item, and empty depth pixels. Actual Blender acceptance
uses before/after forearm renders and regression renders of other equipment. Local evidence stays in ignored workspace.

Acceptance run on 2026-10-02: the reported forearm item rendered all 35 actions and five stored directions
(175 blocks, 1,050 frames), with a passing independent VD alpha/anchor round trip and no clipped or empty frames.
Chest, leg and back-item checks each covered actions 0/4/9/22/25 in all five stored directions (125 frames each),
with the same file-validation result. Representative composites were visually inspected; this is not an in-game
equip test or exhaustive visual approval of every frame. No cloak item was present in the sampled catalog.
The screenshot's action 0, direction 3, frame index 1 now hides the far bracer behind the torso and keeps the near bracer.
Evidence: `workspace/forearm-occlusion-detail.png`, `workspace/forearm-occlusion-comparison.png`,
`workspace/forearm-full-job.txt`, `workspace/occlusion-regression.json` and `workspace/occlusion-regression.png`.
