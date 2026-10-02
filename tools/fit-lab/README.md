# Fit lab

See asset-pack parts on the animated UO body, tune each equipment slot's fit, and hide body faces under clothes
(like CC4's hide-mesh) to stop poke-through. Everything is measured across every item of the slot.

```powershell
python <sidecar>/tools/<pack>/lab_items.py --per-slot 4   # the pack's item list (in the sidecar)
python tools/fit-lab/run.py export --pack <pack>           # Blender: body.glb + items/*.glb + manifest.json
python tools/fit-lab/run.py serve --pack <pack>            # http://127.0.0.1:8774
```

Or `launchers\editor\fit-lab.bat <pack>` (or set `SPRITEMOTION_FIT_PACK`). Data goes to `workspace/ultima-online/fit-lab/<pack>/`. Exports are reused;
`--force` redoes them.

## History, recovery and previews

Adjustments autosave after 800 ms of inactivity; **Save adjustments** saves immediately. Each edit is also cached in
this browser for crash recovery. A slider drag is one history step. **Ctrl+Z** undoes; **Ctrl+Y** or **Ctrl+Shift+Z**
redoes (Command also works on macOS). The History list jumps to any of the last 100 steps. Editing after undo discards
the redo branch. Selection, playback and camera changes are not fit edits. Browser history is scoped to this pack and
server; it survives reloads unless browser storage is cleared or unavailable.

Disk saves atomically replace `lab-adjustments.json` and retain the previous three saved states in
`lab-adjustments-backups/`. **Restore backup** adds an undoable edit and autosaves it. Backups use the same
`schemas/fit-adjustments.schema.json` format as the current file. Unchanged saves do not rotate backups.
Failed writes leave the current file intact.
If another tab or tool changes the disk file, saving pauses: choose **Use disk version** or **Keep my recovered edits**.
The latter deliberately replaces the latest disk version, which is backed up first. The save status reports disk
failures and unavailable browser recovery; do not close with pending changes if browser storage is unavailable.

The local API exposes `GET /api/state` as `{adjustments, revision, backups}`; each backup has `id` and `saved_at`.
`GET /api/backups/<id>` reads one backup. `POST /api/adjustments` takes `{adjustments, base_revision}` and returns
the new state; a stale revision returns HTTP 409 without writing. Revisions hash the canonical JSON content.
The existing `GET /api/adjustments` still returns the plain adjustment document.

Preview cards default to 2× native size with pixelated scaling (up to 4×). **Animate previews** plays their frames
independently of the main viewport; **Cycle directions** advances every two seconds. Pause either control separately.
Choosing a direction stops cycling and selects it for both views. Scrubbing the main frame also positions the preview
frame. These are live fit-lab camera renders, not final Blender output; the same holdout-metric limitations apply.

## In the lab

Preview **Base** selects the original UO sprite, the animated 3D body, or transparent content only.
The original is extracted from the canonical model's embedded original frames; it is a visual reference,
not a final holdout render. `reference.json` follows `schemas/fit-reference.schema.json`, indexes
`reference.png` by `action,frame,stored-direction`, and stays in ignored workspace data. Mirroring applies
to the complete composite. Poke highlighting is separately switchable.

**Stabilize head** holds the head's local rotation and position at the selected action's first frame.
Neck and body movement remains. This preview-only experiment defaults off and does not change saved fits,
the canonical rig, or builds. **Head A/B: 3 per slot** compares the first three item IDs in each slot,
over every frame of checked actions and all five stored directions. The table reports poke counts;
lower counts alone do not establish a better match to original artwork. Download the report for provenance.
The downloadable contact sheet shows the pose with the largest content-pixel change for each item (before/after
pairs); original reference pixels are composited underneath when available. JSON frame indices are zero-based,
and printed contact-sheet frame numbers are one-based. Reports follow `schemas/fit-head-ab.schema.json`.

**Load asset directory** accepts a local directory of already fitted, self-contained GLBs. Select the
destination slot first. Files must have skin weights using the canonical body's bone names; raw FBX and
unrigged objects must go through the pack export/fitting workflow first. Files are copied into an ignored
local import cache; source files are never changed. Imports are session-only and must be loaded again
after reload. `POST /api/assets` takes `{directory, slot, part}` and returns `{items, skipped}` using the
existing manifest item format; `file` paths point into the cache. Limits: 100 GLBs and 50 MB each.

- **Left:** slot and its items. Tick items to show them in 3D; click one to edit its slot.
- **Centre:** the body through the UO camera (drag to orbit, **UO camera** resets), action, direction 0–7
  (5–7 mirrored like the client), frame, play. Below it, scroll across enlarged 136×120 previews of every item in the
  slot, with independent animation and direction cycling. Magenta marks body pixels poking through.
- **Right:**
  - Slot fit: offset, rotation, scale, skinned or rigid binding, plus an offset for one item only.
  - Hide body under clothes: on/off, outward and inward distance.
  - **Measure slot:** poke pixels over every frame of the checked actions in 5 directions. The first measurement is
    the baseline, and each new run shows the change.
  - **Save adjustments** writes `<sidecar>/packs/<pack>/lab-adjustments.json`.

Poke pixels count where body limb and head faces that lie under the item (within 5 cm outside or 3 cm inside it at
rest) show in front of it. Those are the holes the renderer's body holdout would cut (the torso never holds out
there). The renderer's 1 cm holdout margin and 6 mm push-out are not modelled, so the counts run high. Compare them,
don't read them as absolutes.

## From the lab to builds

1. The pack's mapping generator merges `lab-adjustments.json` into the part types (`offset`, `rotate`, `scale`,
   `bind`, `hide_body`). In the sidecar: `<sidecar>/tools/<pack>/make_mapping.py`.
2. `tools/uo-content/blender_build.py` applies the mapped part (`pack_part` in the job settings) as default fit and,
   with `hide_body` enabled, deletes the covered body faces before rendering (`pack_fit.hide_body_under`, the lab's
   rule). The count is written to `scene-report.json`.

Item overrides (`items` in `lab-adjustments.json`) are not used by builds yet.
