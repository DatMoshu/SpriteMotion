---
name: uo-outfit-fit
description: Fit new UO outfit artwork to original animation frames using SpriteMotion region masks, attachment anchors, and explicit facing-dependent occlusion.
---

Read `games/ultima-online/outfit-lab/README.md` and `build.py` in the active
SpriteMotion checkout. Build using original local files and the matching region
mask dataset. Body 400 masks cannot establish compatibility with body 401.

Preserve the 256-square canvas and origin (128,192). Placement is
`(128-centerX, 192-height-centerY)`. Stored facings are SE/S/SW/W/NW;
N/NE/E mirror W/SW/S about x=127.5. Mirror composite artwork and mask together.
Never center each frame on its changing bounding box or stretch frame counts.
Missing/mismatched source sequences stay unavailable and appear in the report.

Separate material fitting from depth. Garment alpha preserves native motion;
selected region IDs subtract pixels that must remain exposed. Masks are 2D
visible-region estimates, not complete hidden anatomy or per-pixel depth.
Background items render first and are occluded by actual body/clothing alpha;
front items render afterward with a specific mask exclusion policy. Art outside
the player silhouette (flags, blades, hats) must not be clipped to the whole body.
Split a complex prop into front/back pieces when one global order is insufficient.

Attach props to per-frame region/pose anchors. A familiar uses an independent
offset and follower lag rather than pretending it is a native equipment layer.
Test crossing facings, overlap, death poses, and absent mask regions explicitly.
Do not advertise the experimental layer policy as a complete UO client renderer.

Run `build.py`, `verify.py`, and the outfit-lab unit tests. Keep source hashes,
source identity, design provenance, missing sequences, and limitations in the
manifest. Consult `uo-outfit-review` for the interactive A/B acceptance pass.
