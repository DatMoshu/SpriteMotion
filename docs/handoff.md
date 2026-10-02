# Handoff: open work

State after the fit-lab / body-hiding / agent-router work. Any agent (Claude, Codex, Cursor, Copilot) can pick this up.
Rules and layout are in `CLAUDE.md`; workflows are the skills in `.claude/skills/`.

## Fit lab editing and recovery

The lab now has Ctrl+Z undo, Ctrl+Y / Ctrl+Shift+Z redo and a 100-step history list. Slider drags form one step.
It caches edits and history in the browser immediately, autosaves after 800 ms idle, and keeps three prior disk saves.
Backups can be restored as undoable edits. Atomic file replacement protects against partial writes; revision checks
pause conflicting saves from other tabs. The UI reports failed saves and offers explicit disk/recovered-version choices.
See `tools/fit-lab/README.md` for storage format, API and limitations.

Preview cards support 2×–4× pixel scaling, independent animation and direction cycling every two seconds. Measurements
pause rendering and editing to keep their pose samples stable. Preview readback uses sRGB to match viewport brightness.
These remain approximate live lab renders, not final Blender sprites.

Preview Base now switches between original UO pixels, the 3D body and transparent content only; poke highlights
are optional. Export extracts the original sprite atlas from the canonical model's embedded frame document.
Directory loading supports fitted, self-contained GLBs with canonical bone names, including weighted dominant-bone
selection for rigid binding. Imports are copied locally and added to the selected slot for the session; raw pack
FBX still requires the existing fitting/export workflow.

Head stabilization is an optional preview experiment, off by default: hold the head's local position/rotation at
the action's first frame, retaining inherited neck/body movement. Inspection found essentially constant local head
translation but substantial local rotation; this is not proof of erroneous noise. A/B on three items in each of
18 slots, all 125 poses across actions 0/4/9/22/25 and five directions, produced 58,964 → 58,652 estimated poke
pixels: eight items improved, six worsened, forty unchanged. Two runs reproduced those counts. Local evidence:
`workspace/head-ab-report.json`, `workspace/head-ab.png`, `workspace/head-motion-inspection.json`. The contact
sheet chooses each item's largest content-pixel difference and labels the pose. These results use the saved fits
at run time (included in the JSON); they are not final Blender render validation or a reason to change rig defaults.

## Verified in the takeover check

- **Studio build with pack fit.** `blender_build.py` reads `pack_mapping` + `pack_part` from job settings, applies the
  part's `offset`/`rotate`/`scale` and runs `pack_fit.hide_body_under` when `hide_body.enabled`. On 2026-10-01,
  two fresh chest preview jobs exercised the studio pipeline with body hiding off and on, using temporary mapping
  copies. Each rendered 125 frames / 25 blocks (actions 0, 4, 9, 22, 25; five stored directions), with no empty or
  clipped frames and a passing independent VD alpha/anchor roundtrip. The enabled run hid 577 body faces.
  Mid-animation stills were compared in all eight facings, including mirrored views; no gross silhouette regression
  was apparent. Across all frames, 482 transparent pixels became visible and 446 visible pixels became transparent;
  these differences are not a poke-through score or proof of improved fit. Local evidence: `workspace/handoff-smoke/`
  (`jobs.json`, `comparison.json`, `comparison.png`). A full 35-action batch, broader slot coverage and nonzero saved
  fit adjustments still need validation.

## Not yet used by builds

- **Lab → mapping.** The sidecar's mapping generator merges `lab-adjustments.json` slot fits. Item overrides
  (`items` in that file) are saved by the lab but not used by builds.

## Known gaps

- The lab's poke metric does not model the renderer's 1 cm holdout margin or 6 mm body push-out (counts run high;
  compare, don't read as absolutes).
- Rig targets marked `proposed_target` in mappings (twist bones, fingers, shield, cloak/skirt chains) are not used by
  `pack_fit.py` yet.
- Untested contributed outfit-lab options: `merge_items.py`, `make_gump_cloak.py`, `build_item.py --planar/--cut`,
  `atlas_to_vd.py --body/--outline`.

## Pending from contributors

- Template-torso masking work (fixes mirrored-direction labels and specks) will be added by its author after the repo
  goes public.

## Housekeeping

- Local branch `backup/pre-sidekick-removal` holds the pre-rewrite history; delete it once the rewrite is accepted.
- Public repository: [DatMoshu/SpriteMotion](https://github.com/DatMoshu/SpriteMotion), configured as `origin`.
  Licensed-pack material lives only in the local sidecar repo (`SPRITEMOTION_SIDECAR`), which must never be pushed.
- Publish only the reviewed `main` branch, never all branches or a mirror.
  The takeover scan of all four commits reachable from `main` found no licensed-pack file paths or prohibited asset
  extensions. It found a generic drive-letter game-folder example in the studio HTML; the current file now uses a
  path-neutral placeholder, and repository checks also scan HTML, JavaScript, CSS, YAML and text files. Older commits
  retain that example placeholder; it is not a discovered user installation path. This was a targeted scan, not an
  exhaustive secret audit.

## Checks

After the preview/reference/import changes: 72 pytest tests passed, one skipped; 15 outfit-lab tests and two Node
history tests passed; routers remain current. Headless Blender exported the original reference and reused the
72 fitted items. Browser checks covered original/model/content-only modes, directory import, stabilization,
full A/B completion, cancellation and return to editing. Reference tests verify exact RGBA pixels and orientation;
import tests verify weighted binding, skeleton mismatch, malformed GLBs and rejection of external resources.

Verification after the editing/recovery changes: 68 pytest tests passed, one client-dependent test skipped; 15 outfit-lab
unittest tests and two Node history tests passed; agent routers are current. Disk tests cover failed replacement,
backup retention/restore, malformed data and concurrent saves. Live browser checks used a separate copy of adjustments
and verified keyboard undo/redo, history jumps, reload recovery, server-outage recovery, conflict resolution, backup
restore/undo, independent playback and repeatable slot measurements. Headless Blender reused the 72-item export
successfully. The normal lab was restarted after saving the open session; the adjustment file's hash was unchanged
across the upgrade. The outfit-lab tests still emit existing unclosed-file ResourceWarnings.

```
python -m pytest -q
python tools/agents/run.py --check
```
