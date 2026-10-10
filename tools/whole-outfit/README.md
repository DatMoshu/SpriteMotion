# Whole-outfit render

Builds every item of an outfit (one preview-coverage job each, the same job the Fit Lab's Render makes) and stacks the
frames over the bare body in client layer order, so faults that only show when pieces meet (a hair piece that renders
empty, a stray strand from a hip piece) are visible in one sheet. Launcher: `launchers/dev/whole-outfit.bat` / `.sh`.

```
python tools/whole-outfit/run.py build     --catalog lab-items.json --adjustments lab-adjustments.json --work DIR ITEM_ID...
python tools/whole-outfit/run.py body      --work DIR
python tools/whole-outfit/run.py composite --catalog lab-items.json --work DIR --out DIR [--direction 2] [--story ID]
```

- `--catalog` is a Fit Lab `lab-items.json`, `--adjustments` its saved fits (or a copy to experiment on).
- `build` needs the canonical model installed in this checkout (`tools/uo-content/pipeline.py setup`) and Blender
  (`SPRITEMOTION_BLENDER`). Jobs land in `workspace/ultima-online/content-studio/jobs/`; their names go to `DIR/jobs.json`.
- `composite` writes one contact sheet per action (5 directions x frames), an all-actions overview, walk and spell GIFs
  and a per-slot table (`validated`, clipped, empty and edge-touching frame counts). Names follow
  `spritemotion_<story>_<subject>_<kind>_<YYYYMMDD-HHMM>.<ext>`.
- A frame whose piece touches the canvas edge is left out of the composite (it is clipped) and counted in the table.

The frames come from a game-derived or licensed pack: keep `DIR` and `--out` under the ignored `workspace/`.
