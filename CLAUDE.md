# SpriteMotion: project rules for coding agents

Shared by every agent (Claude Code, Codex, Cursor, Copilot). Workflows live in `.claude/skills/`; the routers
(`AGENTS.md`, `.github/copilot-instructions.md`, `.cursor/rules/`) are generated from them by
`python tools/agents/run.py`. Edit this file or a skill, never a router.

Open work and where to start: `docs/handoff.md`.

## Never commit

- Game data or anything extracted from a client (`.mul`, `.uop`, `.idx`, frames, renders of game art), or images
  under `games/`. Local work goes in `workspace/` (ignored). `outputs/` is ignored too.
- Licensed third-party assets or their mappings and scripts (commercial asset packs): those live in the local sidecar,
  `SPRITEMOTION_SIDECAR` (default `../SpriteMotion-Sidecar`), which is never pushed.
- Machine paths (a drive-letter path into a user profile, a games folder or a repos folder). Read locations from
  environment variables:
  `SPRITEMOTION_UO_SOURCE` (UO client), `SPRITEMOTION_BLENDER`, `SPRITEMOTION_SIDECAR`.
  `tests/integration/test_repository.py` fails on any of these.

## Layout

The audited CC0 starter models in `examples/cc0-starter` may be committed with their original
license and provenance hashes. This exception does not cover game-derived or commercial assets.

- `common/` is the shared Python package (imports as `spritemotion`); `common/schemas/` holds every JSON data contract.
  Extend a schema (and `docs/`) before emitting a new field.
- `games/<game>/`: adapter, profiles, annotations, equipment slots (`equipment/layers.json`), outfit lab.
- `tools/<job>/` with an entry point (`run.py`) per job; one subfolder per third-party program. No loose scripts.
- `launchers/` groups `.bat` files by job (`editor`, `pipeline`, `dev`; no `game` group, the launcher is `editor/sprite-pose-editor`); every launcher has a one-sentence `rem` line after `@echo off`, calls `launchers/_shared/common.bat` first, never reads stdin, and has a `.sh` twin (LF, executable, sources `_shared/common.sh`). `launchers/README.md` lists them all. `tests/integration/test_repository.py` checks the rule.

## Checks before you finish

```powershell
.venvs\spritemotion\Scripts\python.exe -m pytest -q
cd games\ultima-online\outfit-lab; ..\..\..\.venvs\spritemotion\Scripts\python.exe -m unittest -q
python tools/agents/run.py --check
```

Report what you verified and what you did not. Blender-side changes (`tools/uo-content`, `tools/fit-lab`) need a
headless Blender run, not only a syntax check.

## Key facts

- Canonical body: UO_Model3D v13 (`workspace/ultima-online/canonical-model/model/UO_Body_0x190.blend`), 112 bones
  (the 2026-10 update added `weapon1h.R`, `axe2h.L`, `bow.L`, `polearm.L` to v13's 108), rig `UO_Rig`, direction = driver `-d*pi/4` on the rig's Z rotation, UO frame i = scene frame 1 + 3i.
- In item renders the body is a holdout: body poking through clothing cuts holes in the item sprite. Asset-pack
  parts can hide body faces under them (`hide_body` in the mapping, tuned in `tools/fit-lab`).
- Asset packs are mapped 1:1 per pack: `docs/asset-packs.md`.
