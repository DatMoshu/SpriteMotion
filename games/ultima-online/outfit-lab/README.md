# UO outfit lab

The Astral Wayfarer prototype uses original body-400 animations and equipment
silhouettes, transfers a generated outfit design onto them, and previews original
and custom artwork side by side. Every item has Off / UO / New controls.
The robe and separates share a design; staff and red lightsaber are alternative
weapons. The UO side retains the original broadsword for A/B comparison. The hat
is excluded from the current demo, presets, design gallery and polish scope.
A flag backpack and a floating crystal familiar demonstrate attached props.

## Run

Use Python with Pillow and NumPy. The generated design and local client assets
stay in ignored workspace storage.

```powershell
python games/ultima-online/outfit-lab/build.py --source '<your UO client folder>'
python games/ultima-online/outfit-lab/verify.py workspace/ultima-online/outfit-lab
python -m unittest discover -s games/ultima-online/outfit-lab -p test_fitting.py
python -m http.server 8767 --bind 127.0.0.1 --directory workspace/ultima-online/outfit-lab
```

Open http://127.0.0.1:8767. The generated index.html also works directly from disk.
`--actions 0 4 9 16` makes a smaller build; default is all 35 actions.
Source masks must already exist (see ../region-masks/README.md).

`--config items.json` replaces the built-in ten items. Keys: `items` (`[key, ItemID]`), `cells`, `props`, `hide`,
`drawOrder`, `defaultOff`, `exclusive`, `title`, `displayNames`, and per-item axis fit for slender hand-held items:
`axisFit`, `axisImages`, `axisRatio`, `axisThickness` (constant px), `axisContinuity`, `axisTorsoRule`.
The viewer and `verify.py` read the item list from the manifest. A UTF-8 BOM in the file is accepted.

## Representation

Each action/stored-facing atlas has frames across columns (256 px per frame).
Rows are body, colored mask, then original/new pairs in manifest item order.
The manifest retains graphic IDs, animation IDs, source hashes, missing-sequence
reports, and limitations. Transparent equipment frames remain transparent.
Mismatched sequence counts are hidden, never resampled. Mirrored facings use
the entire composited canvas, matching the x=127.5 pixel reflection.

The historical design sheet is a regular 4-by-3 grid, indexed by DESIGN_CELLS,
with the final cell reserved for a character concept. Its hat cell is skipped.
The separate `--lightsaber` transparent image replaces the original sword design.
It is registered to each native weapon's principal axis, with the nearest visible
hand choosing the hilt end (brightness is the fallback). Source projected length
preserves foreshortening; generated red blade and halo can extend outside the
old sword alpha. Hand-mask subtraction preserves the grip overlap. This is an
estimated 2D registration, especially in small or occluded weapon frames.
The builder splits the clothing sheet's transparent cells,
transfers scanlines onto native silhouettes, retains source fold shading, and
subtracts selected region IDs. This is an automatic 2D texture-fitting baseline;
it does not synthesize an independent back view or recover cloth physics.

Backpack layers use explicit facing rules. Behind-body artwork is occluded by
compositing the actual body and clothing over it; exposed back facings draw the
pack above the torso. The familiar has a body-relative anchor, bob, and optional
lag behind stage movement. Neither prop is a server/client item implementation.

Base frames and pixel origins are authentic; layering is an experimental policy,
and adjustable FPS is a review control rather than UO movement timing. Mounted
actions have no mount sprite. Body 401 and other species require their own masks
and equipment conversions before this workflow can claim support.

Video evidence and handoff live in workspace/ultima-online/outfit-lab/evidence.
No video is produced by this tool.

## Crimson Runner tracksuit

`build_tracksuit.py` builds a separate red outfit with white arm/leg stripes,
independently toggled gold chain, red sneakers and cyan twin-blade energy sword.
The generated assets live in `workspace/ultima-online/tracksuit-lab/` and the
previous outfit remains intact. The top combines native shirt 434 and leather
sleeves 544. Stripe fitting uses visible limb scanlines; necklace art clips to
the torso and is omitted on the rear stored views. Both are 2D approximations.
The chain has no original counterpart in A; choosing UO hides that custom layer.

```powershell
python games/ultima-online/outfit-lab/build_tracksuit.py
python games/ultima-online/outfit-lab/review_tracksuit.py
python -m unittest discover -s games/ultima-online/outfit-lab -p 'test_*.py'
python -m http.server 8768 --bind 127.0.0.1 --directory workspace/ultima-online/tracksuit-lab
```

Use `launchers/editor/tracksuit-lab.bat` for an offline preview.
The builder expects `design.png` (2x2 cells: jacket, pants, chain, shoes) and
`energy-sword.png` (horizontal, grip left). It checks every saved body frame
against fresh decoding; `review_tracksuit.py` checks rear-chain suppression
and generates eight-direction walk and attack contact sheets.

## Spartan armor and directional helmet

`build_spartan.py` creates a separate Master Chief-style armor preview under
`workspace/ultima-online/spartan-lab/`. Six independent armor controls cover
chest, arms, gloves, legs, boots and helmet, plus the existing energy sword.
Original plate animations 527/528/530/529, boots 477 and helmet 563 supply
registration and motion. Clothing uses material transfer, while the helmet
uses five generated directional silhouettes fitted to source helmet bounds.
Rear helmet art has no gold visor. Head pitch and extreme falls remain approximate.

Inputs are `design.png` (3x2: chest/arms/gloves, legs/boots/back chest),
`helmets.png` (5 columns: front, front-side, side, rear-side, rear), and
`energy-sword.png` (grip left). The original demos remain separate.

```powershell
python games/ultima-online/outfit-lab/build_spartan.py
python games/ultima-online/outfit-lab/review_spartan.py
python -m http.server 8769 --bind 127.0.0.1 --directory workspace/ultima-online/spartan-lab
```

`launchers/editor/spartan-lab.bat` opens the offline preview. Evidence is saved
alongside the generated output. The reviewer checks all stored rear-facing helmet
frames for gold visor pixels and generates walk, idle and attack contact sheets.
