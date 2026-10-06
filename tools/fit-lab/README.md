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

Adjustments autosave after 800 ms of inactivity; **Save** saves immediately. Each edit is also cached in
this browser for crash recovery. A slider drag is one history step. **Ctrl+Z** undoes; **Ctrl+Y** or **Ctrl+Shift+Z**
redoes (Command also works on macOS). The History list jumps to any of the last 100 steps. Editing after undo discards
the redo branch. Selection, playback and camera changes are not fit edits. Browser history is scoped to this pack and
server; it survives reloads unless browser storage is cleared or unavailable.

Disk saves atomically replace `lab-adjustments.json` and retain the previous three saved states in
`lab-adjustments-backups/`. **Restore backup** adds an undoable edit and autosaves it. Backups use the same
`common/schemas/fit-adjustments.schema.json` format as the current file. Unchanged saves do not rotate backups.
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

## Blender render pane

Beside the live 3D view, **Blender render** shows the selected item's real renderer output for the current animation,
locked to the main frame and direction (5–7 are mirrored from 3–1, as in the client). **Sprite sheet** shows every
frame of the 5 stored directions; click a cell to jump the lab to that pose, **Download sheet** saves it as a PNG
(item over the original UO body when **UO body** is on), and **Import package** downloads the job's VD package.
The pane uses the newest finished lab render that contains the animation, and compares that job's frozen fit with
the current saved fit: the status reads *Matches the saved fit* or *Fit changed since this render*.
**Render animation** saves, then builds the current animation (coverage `action`) in the background; progress counts
rendered frames. **Auto re-render** (remembered per browser) does this once the saved fit has been still for 3 s and
the shown render is stale or missing, once per fit and pose so a failing build is not retried in a loop.
`GET /api/renders?item=<id>` lists finished renders for an item, newest first (`$defs.renders` in
`common/schemas/fit-lab-build.schema.json`); while building, `GET /api/build` adds `mode`, `started` and `progress`.

## In the lab

### Scoped corrections and masking

The optional `groups` and `corrections` fields extend the adjustment document without changing old saves.
Groups map names to item IDs. Each correction has `target` (pack/slot/group/item), `key` (except pack), optional
`action` (0–34), optional stored `direction` (0–4), and `fit`. Missing filters mean all poses. Offsets and Euler
angles add to the base fit; scales multiply. Resolution order is pack, slot, named groups, individual item;
within each target: all poses, action, direction, action+direction. Groups at equal specificity use name order.
Each selector is unique. Directions 5/6/7 share stored corrections with 3/2/1 respectively.
Corrections are applied to rest geometry before animation, in Blender XYZ coordinates (metres/degrees).
Use **Scoped correction** to edit deltas; the original **Slot fit** remains the base for every pose.
Choosing a pose scope pauses playback/cycling. Groups are created from checked visible items in the current slot.

`occlusion` is clothing (limbs/head only), body (also torso), or none. Back/quiver slots default to body.
Preview overlays use a depth-tested body mask with a 1 cm margin, clipped to the original sprite alpha when present.
Content-only mode uses the same cutout; the 3D view remains a geometry inspection view. The preview still lacks
the final renderer's push-out and exact-outline edge correction, so validate final rendered frames as well.

**Build item** renders the selected mapped source with a snapshot of saved adjustments, using preview, current-action
or full coverage. **Rebuild changed blocks** compares against that item's last successful lab build and produces a
new validated revision. Only blocks present in that build are considered; use Build item for wider coverage.
Neither operation changes the source build. Group corrections affect each member's next build; this button builds
one selected item, not an entire group. Directory-only imports are not build sources.
`POST /api/build` takes `{item, mode: build|rebuild, coverage: preview|action|full, action}`. `GET /api/build`
returns idle/building/complete/failed status, with item, job/review on success, or error on failure. `unchanged`
marks a rebuild with no changed existing blocks. `lab-builds.json` maps item IDs to last-successful job IDs.
Both contracts are described in `common/schemas/fit-lab-build.schema.json`. Successful reviews are served at `/builds/`.

Preview **Base** selects the original UO sprite, the animated 3D body, or transparent content only.
The original is extracted from the canonical model's embedded original frames; it is a visual reference,
not a final holdout render. `reference.json` follows `common/schemas/fit-reference.schema.json`, indexes
`reference.png` by `action,frame,stored-direction`, and stays in ignored workspace data. Mirroring applies
to the complete composite. Poke highlighting is separately switchable.

**Steady head** holds the head's local rotation and position at the selected action's first frame.
Neck and body movement remains. This preview-only experiment defaults off and does not change saved fits,
the canonical rig, or builds. **Run A/B** (Measure tab) compares the first three item IDs in each slot,
over every frame of checked actions and all five stored directions. The table reports poke counts;
lower counts alone do not establish a better match to original artwork. Download the report for provenance.
The downloadable contact sheet shows the pose with the largest content-pixel change for each item (before/after
pairs); original reference pixels are composited underneath when available. JSON frame indices are zero-based,
and printed contact-sheet frame numbers are one-based. Reports follow `common/schemas/fit-head-ab.schema.json`.

**Load fitted GLBs from a folder** accepts a local directory of already fitted, self-contained GLBs. Select the
destination slot first. Files must have skin weights using the canonical body's bone names; raw FBX and
unrigged objects must go through the pack export/fitting workflow first. Files are copied into an ignored
local import cache; source files are never changed. Imports are session-only and must be loaded again
after reload. `POST /api/assets` takes `{directory, slot, part}` and returns `{items, skipped}` using the
existing manifest item format; `file` paths point into the cache. Limits: 100 GLBs and 50 MB each.

- **Top:** pack, save status, undo/redo, save.
- **Left:** slot and its items. Tick items to show them in 3D; click one (or its preview card) to select it.
- **Centre:** the live 3D body through the UO camera (drag to orbit, **UO camera** resets) beside the Blender render
  pane; below them action, direction ring 0–7 (dashed 5–7 are mirrored like the client), play and frame. Below it, scroll across enlarged 136×120 previews of every item in the
  slot, with independent animation and direction cycling. Magenta marks body pixels poking through.
- **Right**, in tabs (Fit, Corrections, Render, Measure, History):
  - Slot fit: offset, rotation, scale, skinned or rigid binding, plus an offset for one item only.
  - Hide body under clothes: on/off, outward and inward distance.
  - **Measure slot:** poke pixels over every frame of the checked actions in 5 directions. The first measurement is
    the baseline, and each new run shows the change.
  - **Save** writes `<sidecar>/packs/<pack>/lab-adjustments.json`.

Poke pixels follow the renderer's body holdout (rule in `web/poke-rules.mjs`, tested by `poke-rules.test.mjs`).
A body pixel counts where the body shows in front of the item by more than an allowance, which is:

- the **1 cm holdout margin** (`HOLDOUT_MARGIN` in the installed canonical renderer's `render_uo_layer.py`; the same
  value the lab already uses for the preview cutout), or in clothing mode with Hide body on, the larger of that and the
  Hide body inward distance (`tools/uo-content/occlusion.py`, `blocked_pixels`), plus
- the **6 mm push-out** (`BODY_GAP` in the same file). It is left out where the build sets it to 0: rigid items and
  helm, weapon, shield, bow, quiver (`tools/uo-content/blender_build.py`), decided from the mapping part's
  `studio_part` (what the build passes the renderer), not the pack part code or layer name; a part with no
  `studio_part` counts as pushed. The push-out moves the item away from the
  body, so adding it to the allowance is an upper bound on the holes it removes.

The item's occlusion mode decides what is counted, as in the renderer: **clothing** counts limb and head faces under
the item (within 5 cm outside or 3 cm inside it at rest; the torso never holds out there), **body** counts the whole
body and ignores Hide body, and **none** counts nothing because the renderer cuts no holes. Counts are lower than
before this rule, so compare runs; don't read them as absolutes. Baselines live only in the open page (Measure
"first" resets on reload), so counts from before this rule are never mixed with new ones.

### Whole outfit while fitting one slot

The rules live in `web/outfit.mjs` (pure logic, tested from pytest with Node in `tests/unit/test_fit_lab_outfit.py`)
and are wired into `lab.js`.

By default the 3D view shows only the slot being edited. **Keep visible** (a checkbox beside the Slot selector)
adds that slot to the *outfit*: its worn item stays rendered in the 3D view when another slot is selected.
The worn item is the slot's selected item; selecting another item in a kept slot changes what it wears.
**Show outfit** (top of the left column) turns every kept slot on or off at once without forgetting them,
so solo and whole-outfit views are one click apart. **Wear set** lists the pack's families (for Sidekick,
one character's modular parts) and keeps, in every slot that has that family, the family's item; slots without
it are left as they were. **Clear outfit** forgets every kept slot.

Rules:

- The edited slot always behaves exactly as today: its ticked items render, the selected item is the one the
  sliders, corrections, Render tab and **Measure slot** act on. A kept slot that is also the edited slot adds
  nothing extra.
- Kept items render with their saved fit (`resolveFit`, current action and direction), are not selectable from
  the 3D view, and do not appear in the item list, preview cards, A/B or builds.
- **Body hiding and poke measurement apply only to the edited slot** (the body hides faces under the edited
  slot's ticked items only, so kept items may show poke-through in the 3D view). **Measure outfit** (Measure tab,
  off by default) changes that: the 3D body hides faces under every shown item, and **Measure slot** counts each
  edited-slot item against the body with all kept items' hidden faces removed and adds one row per kept item
  (kept rows have no baseline until measured once with the option on). Turning it off drops the kept rows.
- Slot preview cards stay per item (solo renders). Outfit compositing in previews is out of scope for now.
- None of this is a fit edit: no history step, no autosave, no change to `lab-adjustments.json`, no effect on
  builds or renders. Keyboard undo/redo never changes the outfit.

The outfit is remembered per browser, per server origin and pack, in `localStorage` key
`fit-lab:outfit:<origin>:<pack>` as the document in `schemas/fit-lab-view.schema.json`:
`{"schema": "spritemotion.fit-lab-view", "schema_version": 1, "show": true, "measure_outfit": false,
"worn": {"<slot>": "<item id>"}}`. On load, entries whose slot or item is not in the manifest (removed imports,
re-exports) are dropped; an unreadable or wrong-version document means an empty outfit. Storage failures
(private window, blocked storage) leave the outfit working for the session only, like the other view toggles.

## From the lab to builds

1. The pack's mapping generator merges `lab-adjustments.json` into the part types (`offset`, `rotate`, `scale`,
   `bind`, `hide_body`). In the sidecar: `<sidecar>/tools/<pack>/make_mapping.py`.
2. `tools/uo-content/blender_build.py` applies the mapped part (`pack_part` in the job settings) as default fit and,
   with `hide_body` enabled, deletes the covered body faces before rendering (`pack_fit.hide_body_under`, the lab's
   rule). The count is written to `scene-report.json`.

Builds snapshot item overrides and scoped corrections from `lab-adjustments.json` at job creation.

Rigid binding selects a separate dominant bone for each mesh, including each half of paired elbow and knee
pieces. Finger articulation requires explicit aligned finger mappings; a hand-only mapping cannot close a glove.
Use `target_end` to match wrist-to-knuckle chains and optional `surface_clearance` for close-fitting shells
(see `docs/asset-packs.md`). Both the exporter and Blender builder use these settings. After a mapping change,
regenerate the GLBs and create new render jobs; existing jobs retain their frozen mapping and fits.

## Garment depth and body hiding

**Front/back depth** changes only the rest-pose front-to-back dimension (Blender Y), before rotation.
Use it for a shallow torso shell instead of increasing uniform Scale and widening the shoulders.
Corrections also have a depth multiplier for individual items, actions and directions.
The same transform is applied in the live preview, initial Blender scene and selective rebuilds.

Body hiding defaults to on when no explicit mapping/saved choice is present. CC0 starter mappings
also enable it by default. An explicitly saved off value remains off. Hiding changes the fitting
body; the complete invisible body still controls camera occlusion in final renders.

### Independent left/right item offsets

The Fit tab provides Left/Right X, Y and Z offsets for an individual item, useful for paired gloves and boots.
These add to the shared fit in Blender XYZ metres before animation. Left/right refer to the character,
not the screen; mirrored UO directions mirror the fitted result. Target-rig bone weights select each side,
including meshes containing both limbs. Neutral bones are unchanged. Each side can be reset separately;
autosave, backups and undo/redo include these offsets. Existing saves default to zero.
The adjustment document stores these as `items.<id>.sides.left` and `.right` three-number vectors.
