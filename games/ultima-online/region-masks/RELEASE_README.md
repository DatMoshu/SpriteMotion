# Body 400 garment-derived region masks — experimental

Local research assets extracted from a user's Ultima Online client. Keep game-derived frames and scenes in the local workspace; do not redistribute them.

Regions: head, neck, torso, upper arms, forearms, hands, hips, thighs, shins and feet. The handoff reports approval of the comparison-sheet masks, anchor, cell layout and bounding boxes. These are garment-derived estimates, not verified anatomical labels.

The unpacked data uses joint-to-joint bone estimates. Overlaps can place shoulders on torso edges and pair merged legs incorrectly. Grey bones have one estimated endpoint and are especially unreliable. Paired limbs are not reliably split left/right. Do not treat these lines as a validated skeleton.

Existing monocular depth experiments do not resolve overlapping limbs. Projected joints and depth from the fitted 3D poses are a proposed next experiment, not a completed correction.

The old RAR uses earlier blob-axis lines and is superseded. No final replacement archive has been produced.

See games/ultima-online/region-masks/README.md in SpriteMotion for provenance and running instructions. Use the canonical scripts there; scripts retained in historical output are snapshots.
