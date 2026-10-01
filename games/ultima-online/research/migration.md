# Migration from UO Roto

The body-400 annotations were first made in *UO Roto*, a standalone Godot
joint lab, and its companion Blender tooling (*UO Armature Lab*). UO Roto was
shared as a bundle that included extracted sprites. **That bundle is not
published and must not be.** Only its joint coordinates were carried over,
after being re-tied to frames that you extract yourself.

Script: [`../migration/migrate_uo_roto.py`](../migration/migrate_uo_roto.py)

```sh
python games/ultima-online/migration/migrate_uo_roto.py --roto "<UO Roto folder>" \
    --dataset workspace/ultima-online/body-400
```

## Mapping

| UO Roto | SpriteMotion |
|---|---|
| `data/actions/action_NNN.json` | `annotations/body-400/estimates/action-NNN.json` |
| `corrections/action_NNN.json` | `annotations/body-400/corrections/action-NNN.json` (meaningful poses only) |
| numeric joint ids 1–20 | `humanoid-20` joint names (`legacy_id` kept in the skeleton) |
| `user_confirmed` | `review.status: approved` |
| `user_notes` | `review.notes` |
| joint status `user corrected` / `mirrored user correction` | `corrected` / `mirrored_correction` |
| action 22, stored directions | `provenance.method: manual`, `independent: true` |
| any `mirrored_from` | `method: mirrored`, with `source_method` and `mirrored_from` |
| all other actions (`estimate_method` rig projection) | `method: rig_projection`, **`independent: false`**, `registration_scale` kept in `parameters` |

## Checks

- **Frame identity by pixels, not index.** For every legacy pose, the
  silhouette of UO Roto's sprite and its recorded placement (centre, size,
  offset) are compared with the frame SpriteMotion extracted. The frame's
  fingerprint is written into the annotation only when they agree.
- **Layers kept apart.** Legacy estimates go only to `estimates/`. Legacy
  user corrections go only to `corrections/`, and only poses that differ from
  their estimate or carry a review status or notes.
- **Round trip.** A verification pass rebuilds each effective legacy pose
  (the correction if present, otherwise the estimate) from the new files and
  compares every coordinate.

Result, recorded in `annotations/body-400/MIGRATION.json`:

- 35 actions and 1,680 poses were compared
- 6 poses are approved: action 22, SE, frames 0–5
- the largest coordinate difference was 0.0, against a tolerance of 0.001

## Preserved facts

- The six approved SE `death_forward` poses are unchanged. The repository
  test `test_bundled_uo_annotations_keep_the_approved_corrections` guards
  them.
- The legacy `limb_identity` notes were copied as they were, including the
  statement that the action-22 A/B labels are provisional. See
  [findings.md §2](findings.md#2-limb-identity-is-inconsistent-across-the-legacy-data).
