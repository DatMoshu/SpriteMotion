---
name: uo-fit-lab
description: Tune how an asset pack's parts fit the UO body per equipment slot (offset, rotation, scale, binding) and hide body faces under clothes (CC4-style) to stop poke-through, measured across every item of the slot in the fit lab.
---

Read `tools/fit-lab/README.md` and `docs/asset-packs.md`. Licensed packs (their mapping, item list, batch scripts)
live in the local sidecar (`SPRITEMOTION_SIDECAR`, default `../SpriteMotion-Sidecar`), never in this repository.

1. Make the pack's item list with the pack's own sidecar script (`<sidecar>/tools/<pack>/lab_items.py`), then
   `python tools/fit-lab/run.py export --pack <pack>` and `python tools/fit-lab/run.py serve --pack <pack>`.
2. In the lab, change one slot at a time. Run **Measure slot** before and after: keep a change only when the slot
   total of poke pixels drops without the contact sheet looking worse. Check several actions and directions.
3. Adjustments autosave; confirm **Saved to disk** (or click **Save adjustments**). Undo/redo and the History list
   recover earlier edits; **Last three saved versions** restores disk backups as undoable edits. Larger previews can
   animate and cycle directions independently of the main viewport; pause them to compare the exact same pose.
   Regenerate the mapping (`make_mapping.py` merges `lab-adjustments.json`), then rebuild a
   preview job and compare its contact sheet. Report numbers, not impressions.
