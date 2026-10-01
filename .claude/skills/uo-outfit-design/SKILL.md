---
name: uo-outfit-design
description: Design coordinated UO clothing and wearable props from original local item references, producing generated artwork and provenance for SpriteMotion outfit fitting.
---

Use the SpriteMotion checkout selected by the user. The reference implementation
is `games/ultima-online/outfit-lab/build.py`; generated art belongs under ignored
`workspace/ultima-online/outfit-lab/`, never with redistributable source code.

Read the outfit-lab README before changing the pipeline. Resolve item graphics
through local tiledata rather than guessing animation IDs. Decode original
equipment at matching body/action/stored-direction/frame and save a reference
sheet. Static props use actual art.mul references; label those separately from
wearable animations. Respect Equipconv.def and stop on unsupported remappings.

Use the imagegen skill for visual redesign. Keep the input reference, exact
prompt, generated output, and hashes. A coordinated set should share material,
trim, and motif; make robe and separates coherent. Do not call a recolor an
independent directional redraw. For this builder, a transparent 4-column,
3-row design sheet holds sword, staff, robe, hat / hair, shirt, pants, shoes /
gloves, backpack, familiar, character concept. Inspect every crop before fitting.

Generated art is a design source, not evidence of accurate game registration.
Pass it to `uo-outfit-fit` for fitting and `uo-outfit-review` for animation QA.
If the user asks for full new silhouettes, generate direction/pose-specific
artwork and supply attachment/depth rules; the existing texture transfer alone
does not satisfy that stronger requirement.
