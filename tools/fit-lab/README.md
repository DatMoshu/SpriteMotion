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

## In the lab

- **Left:** slot and its items. Tick items to show them in 3D; click one to edit its slot.
- **Centre:** the body through the UO camera (drag to orbit, **UO camera** resets), action, direction 0–7
  (5–7 mirrored like the client), frame, play. Below it, every item of the slot rendered at UO size, 136×120, for the
  current pose. Magenta marks body pixels poking through.
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
