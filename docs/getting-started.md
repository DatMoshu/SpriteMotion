# Getting started

## 1. Requirements

| Tool | Needed for | Where it goes |
|---|---|---|
| Python 3.10+ | everything | on `PATH`; the project venv goes in `.venvs/spritemotion/` |
| Godot 4.7 | the Sprite Pose Editor | downloaded into `tools/godot/` by setup ([details](../tools/godot/README.md)) |
| Blender 5.2 LTS (4.2 LTS also tested) | fitting against a model, rendering, comparison | its default install folder, or anywhere via settings ([details](../tools/blender/README.md)) |
| A game you own | real data (optional: the sample needs none) | anywhere; you point the adapter at it |

## 2. Install

Windows:

```bat
launchers\pipeline\0-setup.bat
```

This creates the venv, installs the package, and downloads the tested Godot
build (about 80 MB, checksum verified) unless `SPRITEMOTION_GODOT` points at
one you already have. Install Blender yourself.

Any platform:

```sh
python -m venv .venvs/spritemotion
.venvs/spritemotion/bin/python -m pip install -e ".[test]"      # Windows: .venvs\spritemotion\Scripts\python
.venvs/spritemotion/bin/python -m spritemotion --version
python tools/godot/fetch.py                                       # Godot for the editor
```

The package lives in `common/` and imports as `spritemotion`. Its
command-line interface is `python -m spritemotion <command>`. Run it with
`--help` to list the commands:

| Command | Does |
|---|---|
| `games` | list game adapters and their characters |
| `extract` | read a local game installation into a dataset, then apply the bundled annotations |
| `apply-annotations` / `promote` | move annotations bundle → dataset, or reviewed corrections dataset → bundle |
| `status` / `validate` | coverage, review state and fingerprint mismatches; schema validation |
| `estimate-mirror` / `estimate-rig` | fill estimates from mirror partners, or from a rig projection (marked dependent) |
| `fit` | fit rig poses to annotations and write a pose solution |
| `compare` / `sheet` | silhouette comparison of renders; contact sheets |
| `versions` | list or restore earlier versions of a scene saved by the pipeline |

## 3. Settings and launchers

The Windows launchers are grouped by job:

```text
launchers/_shared/config.bat   the only file you edit
launchers/_shared/common.bat   shared logic (never run directly)
launchers/editor/              sprite-pose-editor.bat (THE launcher), sample-character.bat, open-godot-project.bat
launchers/pipeline/            0-setup, 1-extract-uo, 2-status, 3-fit, 4-key-in-blender, 5-render-views, 6-compare, versions
launchers/dev/                 run-tests, editor-tests, editor-screenshot, blender-smoke, sample-loop, regenerate-sample,
                               install-blender-addon
```

Every setting resolves in this order: **environment variable**, then
`config.bat`, then the built-in default.

| Setting | Default |
|---|---|
| `SPRITEMOTION_PYTHON` | `.venvs\spritemotion\Scripts\python.exe` |
| `SPRITEMOTION_GODOT` | `tools\godot\Godot_v4.7-stable_win64.exe` |
| `SPRITEMOTION_BLENDER` | newest `Blender Foundation\Blender *\blender.exe` under Program Files |
| `SPRITEMOTION_UO_SOURCE` | none: your UO client folder |
| `SPRITEMOTION_DATASET` | `workspace\ultima-online\body-400` |
| `SPRITEMOTION_BLEND`, `SPRITEMOTION_ARMATURE`, `SPRITEMOTION_MAPPING` | your model, its armature, and its rig mapping |
| `SPRITEMOTION_FRAME_START`, `SPRITEMOTION_FRAME_STEP` | `1`, `4`: the Blender frame where source frame *f* is keyed is start + *f*·step |

## 4. First run: the sample character

The sample is a procedural capsule figure with 4 directions and 2 six-frame
sequences. Its true 3D poses are known, so every step can be checked.

```bat
launchers\editor\sample-character.bat
launchers\dev\sample-loop.bat
```

The loop builds `workspace\sample\sample.blend`, exports its rig, fits the
approved `wave` poses, keys them in Blender, renders all four views and
compares them with the sprites. Expect a mean silhouette IoU of about 0.9 and
a keyed reprojection error below 1 px. The sheet it opens shows, for each
frame, the sprite with joints, the render, and the difference:

![Sample comparison sheet](images/sample-wave-compare.png)

## 5. With a real game

For Ultima Online, see [games/ultima-online/README.md](../games/ultima-online/README.md).
In short:

```bat
set SPRITEMOTION_UO_SOURCE=<your UO folder>
launchers\pipeline\1-extract-uo.bat
launchers\editor\sprite-pose-editor.bat
```

Then follow the [reconstruction workflow](reconstruction-workflow.md).

## 6. Tests

```bat
launchers\dev\run-tests.bat       :: pytest; Blender tests run if Blender is found
launchers\dev\editor-tests.bat    :: headless Godot editor suite
launchers\dev\blender-smoke.bat   :: Blender FK / camera / render checks
```

Set `SPRITEMOTION_UO_SOURCE` to also run the test that extracts body 400 from
your client and checks that all 1,680 bundled poses match with no
fingerprint mismatches.
