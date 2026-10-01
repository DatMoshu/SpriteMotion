---
name: uo-outfit-review
description: Review animated UO outfit fitting with per-piece original/new/off comparisons and capture reproducible still evidence for a video-maker handoff.
---

Use the SpriteMotion outfit-lab viewer and read its README. Serve the generated
workspace directory on loopback or open its self-contained index locally.
Use the browser skill for interactive checks; reload after copied viewer edits.

Check all item selectors, robe/separates/bare presets, sword/staff exclusion,
frame stepping, action switches, and all eight facings. Test mask inspection
and moving-player familiar following. Original A and selected B must share
action, direction, frame, camera, and enabled item set. A static item reference
must be labelled static; do not imply it is an original equipped animation.

Run `verify.py`: base-frame byte equality is meaningful independent evidence.
Mask pixel removal proves clipping, not correct anatomy. Inspect garment
appearance visually; numeric overlap alone cannot establish quality. Review
deaths and mounted actions with their known limitations (no mount supplied).

Write evidence under the local outfit workspace: original reference sheet,
generated design and exact prompt, per-item identities and hashes, validation
JSON, full UI screenshots, directional A/B contact sheets, and capture settings.
Give the video maker a shot list with exact actions/facings/presets and a factual
claim ledger separating verified behavior from prototype limitations. Record
failures honestly. Create no video unless the user separately requests one.
