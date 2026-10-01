# Handoff: open work

State after the fit-lab / body-hiding / agent-router work. Any agent (Claude, Codex, Cursor, Copilot) can pick this up.
Rules and layout are in `CLAUDE.md`; workflows are the skills in `.claude/skills/`.

## Done, not yet exercised end to end

- **Studio build with pack fit.** `blender_build.py` reads `pack_mapping` + `pack_part` from job settings, applies the
  part's `offset`/`rotate`/`scale` and runs `pack_fit.hide_body_under` when `hide_body.enabled`. Unit-checked
  (465 faces hidden on a chest test), but no full studio batch has been rendered with it. Run one small batch and
  compare sprites against a run without `hide_body`.
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
- No remote is configured; nothing has been pushed. Licensed-pack material lives only in the local sidecar repo
  (`SPRITEMOTION_SIDECAR`), which must never be pushed.

## Checks

```
python -m pytest -q
python tools/agents/run.py --check
```
