# SpriteMotion

[![CI](https://github.com/DatMoshu/SpriteMotion/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/DatMoshu/SpriteMotion/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<!-- hero-gif -->

**Create, fit and render equipment for Ultima Online's classic 2D characters.**

SpriteMotion is a local content-authoring toolkit. Bring a 3D item, artwork or a
mapped asset pack into the **Content Studio**, adjust its placement on an animated
body in **Fit Lab**, and use Blender to produce transparent equipment frames and
client import packages. Your models, game data and generated content stay on your
machine.

**Status: public development preview.** The tools are available now; fitting and
rendering still need broader animation and in-game validation. This is not yet a
one-click installation or a guarantee that every item fits every animation.

## The tools

| Tool | What it does |
|---|---|
| [Content Studio](tools/uo-content/README.md) | Imports equipment models, applies artwork to templates, configures builds and reviews rendered animations. |
| [Fit Lab](tools/fit-lab/README.md) | Previews mapped parts on the animated body; adjusts slot offset, rotation, scale and binding; tunes body hiding under clothing. |
| [Blender build pipeline](tools/uo-content/README.md#outputs-and-importing) | Produces transparent PNG frames, an editable item scene, VD animation data, review sheets and import packages. |
| [Client staging tools](tools/uo-content/README.md#outputs-and-importing) | Prepare new client files and equipment definitions for review without modifying the source client installation. |
| [Sprite Pose Editor](tools/sprite-pose-editor/README.md) | The earlier reconstruction workflow: annotate original sprites and fit a rig to those measurements. Still available for research and annotation. |

Fit Lab includes undo/redo, a 100-step history, autosave, browser crash recovery
and the previous three disk saves. Enlarged previews can animate and cycle
directions independently, with original UO pixels, a 3D body or content-only views.
It can also load a folder of already fitted, self-contained GLBs. See the
[Fit Lab guide](tools/fit-lab/README.md) for requirements and recovery behavior.

Text input configures equipment templates; pictures supply template artwork.
Neither is an unrestricted text-to-3D or single-image reconstruction system.
Agent-assisted artwork and geometry can enter through the same asset pipeline.

## Start with Content Studio

You need **Python 3.10+**, **Blender 4.2+**, and a separately obtained, compatible
**UO_Model3D** source folder for the current UO equipment workflow. The reference
model and its artwork are not included in this repository. Godot is only needed
for the separate Sprite Pose Editor or a GUO host, not the standalone web tools.

From a checkout, on Windows:

```powershell
py -3 -m venv .venvs/spritemotion
.venvs/spritemotion/Scripts/python.exe -m pip install -e ".[test]"
.venvs/spritemotion/Scripts/python.exe tools/uo-content/pipeline.py setup --source "<extracted-model-folder>"
launchers/editor/content-studio.bat
```

Open **http://127.0.0.1:8772**. Choose an equipment type, supply an asset or configure
a template, then make a preview build before attempting a full build. Review the
result across actions and directions before staging it for a client/server test.
Set `SPRITEMOTION_BLENDER` if Blender cannot be found automatically. See the
[Content Studio guide](tools/uo-content/README.md) for model inputs, configuration,
outputs and import limitations.

On other platforms, create and activate a Python environment, run
`python -m pip install -e ".[test]"`, then use the same Python setup command and
`python tools/uo-content/studio.py`.

## Try the CC0 starter equipment

[Bundled CC0 examples](examples/cc0-starter/README.md) cover all 25 UO layer routes,
with animated wearables, jewelry source/paperdoll examples and mount guidance.
After the Python, Blender and local model setup above, run
`launchers/editor/workbench.bat cc0-starter` on Windows or
`sh launchers/editor/workbench.sh cc0-starter` on Linux. The workbench prepares the
starter lab export when needed and starts Studio and Fit Lab.
See [all launchers](launchers/editor/README.md).

## Open Fit Lab

Fit Lab needs a prepared asset-pack mapping, item list and Blender export.
Commercial packs and their pack-specific scripts belong in a private local
sidecar; they are not supplied by the public repository. Follow the
[asset-pack setup guide](docs/asset-packs.md) and [Fit Lab export instructions](tools/fit-lab/README.md)
first, then run:

```bat
launchers\editor\fit-lab.bat <pack>
```

Open **http://127.0.0.1:8774**. The launcher reuses an existing export; it does not
prepare an arbitrary folder of raw models automatically. You can also set
`SPRITEMOTION_FIT_PACK` instead of passing the pack name.

Live previews help compare fits. Their poke-through measurements are approximate
and do not reproduce every Blender holdout or push-out rule. Final rendered frames
and an in-game test are the acceptance checks.

## Published code and ongoing work

The instructions above describe the public `main` branch. More recent fitting
and rendering changes may be on development branches or in
[open pull requests](https://github.com/DatMoshu/SpriteMotion/pulls).

Fit Lab supports scoped animation/direction corrections, Blender render review,
body holdouts, front/back depth and independent left/right item offsets.
A shared Fit Lab inside [GUO](https://github.com/DatMoshu/GodotUO) has been tested
locally; its distribution and fresh-install onboarding are still in development.
Do not assume a SpriteMotion checkout installs the GUO integration.

## What you download

**Included:** Python and Blender tools, the web editors, game adapters, schemas,
annotation data, agent instructions, a redistributable procedural sample and
audited CC0 starter equipment with licenses and provenance hashes.

**Not included:** UO client files, extracted sprites, the canonical body scene,
commercial asset packs, private mappings, or generated game content. Work files
and renders belong under ignored `workspace/` or `outputs/` directories. Supply
your own permitted inputs; the public code download is not a bundled UO art pack.

To explore the original reconstruction workflow without game assets, use the
[procedural sample and getting-started guide](docs/getting-started.md). The
[reconstruction workflow](docs/reconstruction-workflow.md) and
[annotation format](docs/annotation-format.md) remain documented separately.

## Help wanted: toward UO parity

The tools work; proving that every item looks right in every animation, facing and client is the open part.
[ROADMAP.md](ROADMAP.md) lists the render acceptance gates, what is already done and where help is wanted:
acceptance matrices across all 35 actions, rig targets for twist bones and cloth chains, complete-outfit reviews
and in-game client tests. Setup walkthroughs live in the [wiki](https://github.com/DatMoshu/SpriteMotion/wiki);
questions go to [Discussions](https://github.com/DatMoshu/SpriteMotion/discussions). Report a pose that does not
match original equipment with the **Parity gap** issue template, and read [CONTRIBUTING.md](CONTRIBUTING.md)
before opening a pull request.

## Contributing

Use a branch or fork and submit a pull request. Protected `main` requires the
`guard` and `build` checks and maintainer code-owner approval; administrators
retain a bypass. See [CONTRIBUTING.md](CONTRIBUTING.md) for review and content rules,
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards and [SECURITY.md](SECURITY.md) for
reporting vulnerabilities.

```powershell
python -m pytest -q
python -m unittest discover -s games/ultima-online/outfit-lab -q
python tools/agents/run.py --check
```

Hosted CI checks the source workflow and package build. It does not certify
proprietary-model rendering or in-game behavior. Include actual render evidence
for fitting changes, and keep private artwork and data out of commits.

## License

Code, schemas, documentation and annotations: **MIT**, see [LICENSE](LICENSE).
Third-party software is listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Game names are trademarks of their owners. This project is not affiliated with
or endorsed by them.
