# Launchers

Everything a person runs is a `.bat` here (Windows) with a `.sh` twin of the same name (Linux and macOS, `bash`).
SpriteMotion has no game, so there is no `game/` group: **the launcher is `editor/sprite-pose-editor`**, which opens the Sprite Pose Editor.

Settings resolve: environment variable > `_shared/config.local.sh` (`.sh` only, git-ignored) > `_shared/config.bat` / `_shared/config.sh`.
Launchers never read stdin and never hardcode a path. Long-running ones stay in the foreground (Ctrl+C stops them);
only GUI programs (Godot, an image viewer, a browser page) are detached, and their description says so.

What a launcher must look like (checked by `tests/integration/test_repository.py`):

- `.bat`: CRLF; first line `@echo off`; then one `rem` sentence saying what it does and what you see; optionally `rem args: ...`; then `call "%~dp0..\_shared\common.bat" || exit /b 1`.
- `.sh`: LF, executable bit in git, `#!/usr/bin/env bash`, the same sentence as the first `#` line, an optional `# args:` line, `set -euo pipefail`, then it sources `_shared/common.sh`.
- No `pause`, `set /p` or `choice`. Exit code 0 on success, non-zero otherwise.

Content tools (Content Studio, Fit Lab, the workbench) are described in [editor/README.md](editor/README.md).
`editor/content-studio.ps1` and `editor/female-live-pose.ps1` are older PowerShell entry points kept as they were; the deck lists only `.bat`.

## Editors and long-running tools

| Launcher | What it does | Arguments |
|---|---|---|
| `editor/content-studio` | Start Content Studio (build a UO item from a prompt, picture or model) on http://127.0.0.1:8772 and keep it running here until Ctrl+C. |  |
| `editor/female-live-pose` | Start the live pose editor server on http://127.0.0.1:8768/editor/ and keep it running here until Ctrl+C. | `[--port N]  (default 8768)` |
| `editor/fit-lab` | Start Fit Lab (asset-pack slot fitting and body hiding) for a pack on http://127.0.0.1:8774 and keep it running here until Ctrl+C. | `<pack>  (or set SPRITEMOTION_FIT_PACK)` |
| `editor/open-godot-project` | Open the Sprite Pose Editor's source project in the Godot editor (starts the editor window and returns). |  |
| `editor/outfit-lab` | Open the outfit lab page (workspace\ultima-online\outfit-lab\index.html) in your browser, or say how to build it when it is missing. |  |
| `editor/overalls-lab` | Open the overalls lab page (workspace\ultima-online\overalls-lab\index.html) in your browser, or say how to build it when it is missing. |  |
| `editor/sample-character` | Open the Sprite Pose Editor (a Godot window) on the bundled, redistributable sample character. |  |
| `editor/plate-armor-lab` | Open the sci-fi plate armor lab page (workspace\ultima-online\plate-armor-lab\index.html) in your browser, or say how to build it when it is missing. |  |
| `editor/sprite-pose-editor` | THE launcher: open the Sprite Pose Editor (a Godot window that opens and returns) on a dataset. | `[dataset folder]  (default: SPRITEMOTION_DATASET)` |
| `editor/tracksuit-lab` | Open the tracksuit lab page (workspace\ultima-online\tracksuit-lab\index.html) in your browser, or say how to build it when it is missing. |  |
| `editor/workbench` | Start Content Studio and Fit Lab together for a pack, open both in your browser, and keep them running here until Ctrl+C. | `[pack]  (default: SPRITEMOTION_FIT_PACK, else the bundled cc0-starter)` |

## Data pipeline steps (numbered in order, then single jobs)

| Launcher | What it does | Arguments |
|---|---|---|
| `pipeline/0-setup` | Create .venvs\spritemotion, install SpriteMotion (editable, with test extras) and fetch the tested Godot build into tools\godot unless SPRITEMOTION_GODOT is set. |  |
| `pipeline/1-extract-uo` | Extract a character from YOUR UO client into workspace\ and apply the bundled annotations, then print its status. | `[character]  (default: body-400)` |
| `pipeline/2-status` | Print annotation coverage, review state and fingerprint mismatches for a dataset (exit 1 when it does not validate). | `[dataset]  (default: SPRITEMOTION_DATASET)` |
| `pipeline/3-fit` | Export your model's rig from Blender, then fit one sequence to the dataset's annotations (writes workspace\fits\rig.json and workspace\fits\<sequence>.json). | `<sequence, e.g. action-022> [approved\|independent\|all]` |
| `pipeline/4-key-in-blender` | Key a fit into your model as action fit_<sequence> and report the reprojection error Blender produces (saves into SPRITEMOTION_BLEND, keeping the previous file in <model>.versions). | `<sequence> ["note for this version"]` |
| `pipeline/5-render-views` | Render an action of your model from every sprite direction through the dataset camera into workspace\renders\<action>\<sequence>. | `<sequence> [action]  (default action: fit_<sequence>)` |
| `pipeline/6-compare` | Score the silhouette match and build a contact sheet (sprite, render, difference) for one sequence, then open the sheet; scores are also recorded on the model version. | `<sequence> [action]  (default action: fit_<sequence>)` |
| `pipeline/creature-build` | Reshape a CC4 base into a creature in headless Blender and save the result as a .blend. | `--config <json> --save <out.blend>` |
| `pipeline/fit-lab-export` | Export a pack for Fit Lab into workspace\ultima-online\fit-lab\<pack> (body, items, manifest) and print the result. | `--pack <pack> [--force]` |
| `pipeline/silhouette-fit` | Run the silhouette-constrained fit (prep, then fit) on a dataset and print the fit summary. | `prep --dataset <d> --poses <dir> --out <work> \| fit --dataset <work> --rig <json> --mapping <json> --camera <json> --out <dir>` |
| `pipeline/starter-assets` | Build the bundled CC0 starter equipment (or export it to Fit Lab with --prepare-lab) and print what it produced. | `[item] [--list] [--prepare-lab] [--smoke]` |
| `pipeline/transfer-export` | Export a finished uo-content build job as a transfer artifact (transfer.json plus cropped frames) and read it back to check it. | `--job <job dir> --out <new empty dir>` |
| `pipeline/uo-content` | Run the uo-content build pipeline (setup, build, finish, rebuild) and print what it wrote. | `setup --source <UO_Model3D folder> \| build --spec <json> [--asset <glb>] \| finish <job> \| rebuild <job> --adjustments <json>` |
| `pipeline/versions` | List the saved versions of your model (SPRITEMOTION_BLEND) with when, what made each one and its scores, or make an earlier one current again. | `[restore <N>]  (no argument lists)` |

## Development: tests, gates, smoke checks

| Launcher | What it does | Arguments |
|---|---|---|
| `dev/agents-check` | Check that the generated agent routers (AGENTS.md, Copilot, Cursor) match CLAUDE.md and the skills; exit 1 when one is stale. |  |
| `dev/all-gates` | Run the three CLAUDE.md checks in order (pytest, outfit-lab unittest, agents check) and exit non-zero if any fails. |  |
| `dev/blender-smoke` | Run the headless Blender smoke checks (FK agreement, rig export, camera projection, render placement); results land in workspace\blender-smoke. |  |
| `dev/editor-screenshot` | Capture the Sprite Pose Editor on a dataset to workspace\screenshots\editor.png and print where it went. | `[dataset]  (default: examples\sample-character)` |
| `dev/editor-tests` | Run the headless Sprite Pose Editor tests and print the result (report: tools\sprite-pose-editor\tests\output\test-report.json). |  |
| `dev/fit-lab-web-tests` | Run the Fit Lab browser-code tests (node --test in tools\fit-lab\web) and print the result. |  |
| `dev/install-blender-addon` | Install the SpriteMotion sheet add-on into your Blender (SPRITEMOTION_BLENDER) and enable it; this changes your Blender preferences. |  |
| `dev/outfit-lab-tests` | Run the outfit-lab unittest suite (games\ultima-online\outfit-lab) and print the result. |  |
| `dev/regenerate-sample` | Regenerate examples\sample-character (deterministic; the tests check it matches what is committed). |  |
| `dev/run-tests` | Run the Python test suite (Blender tests run when Blender is found, the UO test when SPRITEMOTION_UO_SOURCE is set). | `[pytest arguments]  e.g. -k sample` |
| `dev/sample-loop` | Run the whole loop on the procedural sample (build .blend, export rig, fit, key, render, compare) into workspace\sample, then open the wave sheet. |  |
| `dev/transfer-fixture` | Regenerate the synthetic transfer-artifact fixture in tests\fixtures\transfer (deterministic, no game data). | `[--out dir]  (default: tests/fixtures/transfer)` |

## Not launchers

- Fit Lab's poke **Measure** runs in the browser (there is no command line for it), so it has no launcher: start `editor/fit-lab` and press Measure.
- `tools/vd/vdtool.py`, `tools/vd/mul2vd.py` and `tools/godot/fetch.py` are helper scripts with their own usage in `tools/vd/README.md` and `tools/godot/README.md` (`pipeline/0-setup` calls `fetch.py`).
- `games/ultima-online/outfit-lab/build_*.py` take per-outfit arguments and are documented in that folder's README.
