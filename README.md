# SpriteMotion

**Try bundled CC0 assets:** [starter assets for every UO layer](examples/cc0-starter/README.md) include textures and starter presets. Choose a bundled starter in Content Studio, or upload your own GLB.

**Create new UO content:** the [Content studio](tools/uo-content/README.md) accepts text-configured item templates, pictures and 3D models, mounts equipment on the shared **UO_Model3D v13** rig, renders animations and exports VD plus classic-client import packages. Start with `launchers/editor/content-studio.bat`. This is the active item-authoring workflow; the reconstruction tools documented below remain available as historical research and annotation utilities.

**Development status:** the tools are public; UO equipment rendering is still undergoing broader animation and
in-game validation. See the [render acceptance and release roadmap](docs/render-release-roadmap.md).

Reconstruct editable 3D characters and animations from existing 2D sprites, so
artists can create compatible new animation frames, clothing, and equipment.

Classic 2D games drew each character from a few fixed directions. SpriteMotion
reads those frames from a game you own, lets people mark where the joints are,
and fits a 3D rig to those marks. The fitted poses go into Blender, where they
are rendered back through the game's camera and compared with the original
sprites. Each pass through this loop makes the 3D version a little more
faithful. Once it matches, new frames, outfits and weapons can be rendered
from the model and still line up with the original art.

![Sprite Pose Editor on the sample character](docs/images/sample-character-editor.png)

## What is in the repository, and what is not

| Included | Not included, ever |
|---|---|
| Tools: the Sprite Pose Editor (Godot), the Python pipeline, and Blender scripts | Game files, extracted sprites, renders or sprite sheets |
| Per-game **adapters** that read *your* local installation | Models, `.blend` scenes, rigs from a game |
| **Annotations**: joint coordinates, with provenance and fingerprints | Anything under `workspace/` (your local working area) |
| A procedural sample character, drawn by our own script | |

Annotations are numbers: joint positions and a SHA-256 fingerprint of the frame
they were drawn on. They only become useful next to art you extract yourself.
When the art differs from what an annotation was drawn for, the annotation is
reported as a mismatch and not applied. See
[docs/annotation-format.md](docs/annotation-format.md).

## Layout

```text
common/                  shared Python package (imports as `spritemotion`); knows nothing about any game
schemas/                 JSON Schemas for datasets, skeletons, annotations and game descriptions
tools/sprite-pose-editor Godot 4.7 editor for reviewing and correcting joint annotations
tools/blender/           Blender scripts: export rig/actions, key fitted poses, render every view
tools/godot/             where the Godot executable goes (not committed)
games/<game>/            adapter, profiles, skeletons, bundled annotations, recipes, research
examples/sample-character  redistributable procedural character for trying the whole loop
launchers/               Windows .bat launchers (edit launchers/_shared/config.bat only)
tests/                   pytest suite (unit + integration, Blender tests when Blender is present)
workspace/               your local data: extracted frames, models, fits, renders (gitignored)
```

Supported games: [Ultima Online](games/ultima-online/README.md) (classic 2D
client, human male body 400, all 35 actions, 1,680 annotated frames).

## Quick start

Requirements: Python 3.10+, [Godot 4.7](tools/godot/README.md) for the editor,
and [Blender 5.2 LTS or 4.2 LTS](tools/blender/README.md) for reconstruction.

```bat
launchers\pipeline\0-setup.bat          :: creates .venvs\spritemotion
launchers\dev\run-tests.bat
launchers\editor\sample-character.bat   :: open the editor on the sample
launchers\dev\sample-loop.bat           :: fit -> Blender -> render -> compare, on the sample
```

On other platforms, see [docs/getting-started.md](docs/getting-started.md);
every launcher is a thin wrapper around a documented command.

With your own Ultima Online client:

```bat
set SPRITEMOTION_UO_SOURCE=<your UO folder with anim.mul>
launchers\pipeline\1-extract-uo.bat     :: extract body 400 and apply the bundled annotations
launchers\editor\sprite-pose-editor.bat
```

## Documentation

- [Getting started](docs/getting-started.md): install, launchers, first run
- [Reconstruction workflow](docs/reconstruction-workflow.md): annotate, fit, key, render, compare, iterate
- [Annotation format](docs/annotation-format.md): layers, provenance, fingerprints, review
- [Adding a game](docs/adding-a-game.md): writing an adapter and a profile
- [Sprite Pose Editor](tools/sprite-pose-editor/README.md)
- [Contributing](CONTRIBUTING.md), including how to submit annotations

## Principles

- **Corrections are separate from estimates.** Automatic estimates are
  starting points kept in their own layer. Anything a person changed, reviewed
  or approved goes in the correction layer. The effective pose is the
  correction if there is one, otherwise the estimate.
- **Evidence is labelled.** Every pose records how it was made. Poses
  projected from a 3D rig are marked `independent: false`, and fitting refuses
  to use them as targets unless explicitly told to. A rig cannot validate
  itself.
- **Nothing is guessed.** Annotations are matched to frames by identity and
  fingerprint. Mismatches are reported, not silently applied.
- **Overlap is not completion.** Silhouette IoU measures shape agreement, not
  anatomy, timing or correctness.

## License

Code, schemas, documentation and annotations: MIT, see [LICENSE](LICENSE).
Third-party software is listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Game names are trademarks of their owners. This project is not affiliated
with or endorsed by them.
