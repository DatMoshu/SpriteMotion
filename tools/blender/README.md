# Blender scripts

These scripts reconstruct and check scenes from assets you supply locally.
The repository ships no `.blend` files. Every script runs headless inside
Blender (tested with 4.2 LTS and 5.2 LTS) and takes its arguments after `--`:

```sh
blender -b --factory-startup [scene.blend] --python tools/blender/<script>.py -- [options]
```

Use `--factory-startup` so that your own add-ons do not load. It keeps runs
reproducible, and some add-ons crash Blender on exit in background mode. The
launchers do this for you (`SPRITEMOTION_BLENDER` selects the executable).

| Script | Does |
|---|---|
| `export_rig.py --out rig.json [--armature NAME]` | rest pose → `spritemotion.rig` |
| `export_action.py --out pose.json --frames N [--action NAME --frame-start S --frame-step K --mapping M]` | samples an existing action → pose solution (a seed for `fit`) |
| `apply_solution.py --solution fit.json [--action NAME [--copy-from ACTION] --mapping M --dataset D --camera C --report R --save out.blend --note TEXT]` | keys a pose solution into a new action (an existing action of that name is kept as `NAME.vNNN`). Each fitted bone is keyed by its pose-space matrix, parents first, so constraints on helper bones (Rigify follow/hinge parents) cannot move the result. `--copy-from` starts the action as a copy of an existing clip, keeping the channels the fit does not touch. It reports Blender-vs-solver FK error and the reprojection error of the posed joints against the annotations. `--save` keeps the previous file as a version. |
| `render_views.py --dataset D --sequence S --out DIR [--action NAME --frames --directions --camera --turn-object --all-objects --keep-render-settings]` | sets up the dataset camera and renders every frame in every stored direction at canvas size. Only the character is rendered (the armature, its children and the meshes it deforms) unless `--all-objects` is given, so stages and backdrops stay out of the silhouette. Mirrored-only views are not rendered: `compare` and `sheet` flip the partner's render, as the game does. |
| `tests/smoke_test.py [--out DIR]` | 6 checks: FK agreement, rig export, 3 camera setups, render placement |
| `smblender.py` | shared helpers. It puts `common/` on `sys.path` as `spritemotion`, so Blender's Python needs no pip install. |

Blender's bundled Python has numpy but not Pillow. The scripts only use the
parts of `spritemotion` that do not need Pillow.

Rendered views default to flat, unfiltered Workbench silhouettes. This keeps
the edges at single-pixel accuracy, so the silhouette comparison measures
shape and not shading. `--keep-render-settings` renders with your scene's
own engine and look, for example when rendering equipment layers.

## Scene versions

Every `--save` through `apply_solution.py` keeps what it replaces, so an
animation that was better before a pass is never lost:

```text
model.blend                        current version
model.versions/history.json        per version: when, what made it, note, metrics
model.versions/model.v001.blend    earlier versions
```

Inside the file, re-keying action `fit_022` renames the old one to
`fit_022.v001` (with a fake user) before keying the new one, so both passes
can be compared in the Action editor. A file saved by hand in Blender between
passes is archived too, recorded as an external save.

```sh
python -m spritemotion versions list model.blend
python -m spritemotion versions restore model.blend --version 3
python -m spritemotion compare DATASET --renders DIR --attach model.blend --label fit_022
```

`restore` archives the current file before bringing the old one back, so it
can be undone. `compare --attach` stores the silhouette scores on the current
version, and `versions list` shows them next to each version. The launcher is
`launchers\pipeline\versions.bat`.

Timeline: source frame *f* is keyed and rendered at Blender frame
`frame-start + f × frame-step`.

The full procedure is in
[docs/reconstruction-workflow.md](../../docs/reconstruction-workflow.md). The
end-to-end test is `tests/integration/test_blender_loop.py`.

## Which Blender is used

In order:

1. the `SPRITEMOTION_BLENDER` environment variable, or
   `launchers/_shared/config.bat`
2. `blender` on `PATH` (tests only)
3. the newest `Blender Foundation/Blender */blender.exe` under Program Files

Tested with Blender 4.2 LTS and 5.2 LTS (5.2.2). 4.2 is out of support
since July 2026; use 5.2 LTS for new work. A `.blend` saved by 5.2 may not
open correctly in 4.2, so switch a whole project at once.
