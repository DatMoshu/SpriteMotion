# Adding a game

A game is a folder under `games/`. The shared layer (`common/`) never imports
game code by name. It reads `games/<game>/game.json` and loads the adapter
from the file that `game.json` names. Adding a game therefore adds files only
under `games/<game>/`.

```text
games/<game>/
  README.md              what is supported, where the user points the extractor, known limits
  game.json              descriptor (schemas/game.schema.json)
  extraction/            the adapter: local game files -> normalized dataset
  profiles/              per character: canvas, directions, camera; optional sequence catalog
  skeletons/             skeleton(s) and rig mappings
  annotations/<char>/    bundled estimates/ and corrections/ (coordinates only)
  recipes/               how-tos specific to this game (export conventions, layer order)
  research/              what is known about the game's projection and conventions, with evidence
```

[`games/ultima-online/`](../games/ultima-online/README.md) is the reference
implementation.

## 1. game.json

```json
{
  "schema": "spritemotion.game", "schema_version": 1,
  "id": "my-game",
  "title": "My Game",
  "adapter": {"module": "extraction/my_adapter.py", "class": "MyGameAdapter"},
  "source_hint": "The folder containing sprites.dat",
  "characters": [
    {"id": "hero", "title": "Hero", "profile": "profiles/hero.json",
     "skeleton": "skeletons/humanoid.json", "annotations": "annotations/hero"}
  ]
}
```

Paths are relative to the game folder. `python -m spritemotion games` lists
what it finds.

## 2. The adapter

Subclass `spritemotion.sprites.adapter.GameAdapter` and implement `extract`:

```python
from spritemotion.sprites import Dataset, blank_canvas, place, mirror_canvas, fingerprint, frame_id, opaque_bounds, save_png
from spritemotion.sprites.adapter import GameAdapter

class MyGameAdapter(GameAdapter):
    def extract(self, source, character_id, out_dir, sequences=None):
        character = self.character(character_id)
        ...  # decode the user's files, write frames + skeleton.json + dataset.json
        return out_dir / "dataset.json"
```

Your `extract` must do the following:

1. **Normalize every frame onto one fixed canvas**, so that the character's
   ground origin is always at `canvas.anchor`. Use the game's own placement
   rule, meaning whatever the game does when it draws the sprite at a world
   position. Joints in all frames and directions then share a coordinate
   system, and a 3D camera can be fitted.
2. **Produce the views the game produces.** If the game mirrors a stored view
   at draw time, mirror the placed canvas about `mirror_axis_x`
   (`mirror_canvas`). Record `mirrored_from` on those frames and `mirror_of`
   and `stored: false` on those directions.
3. **Fingerprint the normalized canvas** with `fingerprint(image)`. Use the
   neutral form of the image: for example unhued, no palette effects, no
   per-player tint. Annotations are tied to that fingerprint.
4. **Give every frame a stable id**: `frame_id(dataset_id, sequence, direction, frame)`.
   `dataset_id` is `<game>/<character>`. Sequence ids must not change once
   annotations exist.
5. **Give each direction a `facing`** in world XY (x east, y north), so the
   fitter knows which way to turn the model for that view.
6. Write `skeleton.json` (copy the character's skeleton) and `dataset.json`.
   Then call `Dataset.load(path)` to validate the schema and frame identity.
7. **Fail clearly** on formats you do not support, for example a patched or
   newer container format. Do not guess.
8. Never write anything outside `out_dir`, and never copy game files into
   the repository.

`extract` in the CLI then applies the character's bundled annotations. Poses
whose fingerprints do not match are reported, not applied.

## 3. The profile

The profile is game-specific: your adapter reads it. It usually holds:

- `canvas`: `width`, `height`, `anchor`, `mirror_axis_x`
- `directions`: id, name, `facing`, and whatever maps them to the stored data
- `camera`: an affine orthographic camera, or a path to one. Start from the
  game's *ground* projection, meaning where one world unit east, north and up
  lands on screen. Record in `research/` whether the character art was
  actually drawn with that projection. Often it was not.
- anything else the adapter needs, such as file ids, action tables or frame
  timing

## 4. Skeleton and mappings

Choose joints that can be seen on the sprites at their size. If the art often
hides which limb is which, use neutral chain names (`arm_A`, `arm_B`) and
state the convention in each annotation file's `limb_identity`. Add rig
mappings under `skeletons/rig-mappings/` for the rigs people are likely to
use.

## 5. Annotations

Begin with estimates: mirror partners, or rig projections labelled
`independent: false`. People then correct and approve poses in the editor,
and the reviewed corrections are promoted into
`annotations/<character>/corrections/`. If you are importing annotations from
an older tool, write a migration script that does the following (see
`games/ultima-online/migration/`):

- ties each legacy pose to a frame by checking its pixels, not only its
  index
- keeps the legacy estimates and the legacy user corrections in separate
  layers
- labels provenance honestly
- verifies that the new files reproduce every effective legacy pose

## 6. Tests

Add a unit test that builds a tiny synthetic game file in memory and runs
your adapter on it (see `tests/unit/test_uo_adapter.py`). Real game files are
never in the repository, so the tests must not need them. Add an optional
integration test, guarded by an environment variable such as
`SPRITEMOTION_<GAME>_SOURCE`, that extracts from a real installation and
checks the bundled annotations match with zero mismatches.
