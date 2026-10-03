# Contributing

Thanks for helping. SpriteMotion accepts three kinds of contribution: code,
annotations, and research notes. Each has its own rules below.

## Pull requests and protected main

Work on a branch (or a fork) and open a pull request targeting `main`.
Merging requires the `guard` and `build` checks plus one code-owner approval
from @DatMoshu. New commits dismiss stale approvals. Force pushes and deletion
of `main` are blocked; merged working branches are deleted automatically.
As in GUO, administrators retain a bypass for maintainer changes and recovery.
Contributors cannot approve their own pull requests. CI uses read-only tokens;
GitHub Actions cannot approve pull requests.

The checks cover repository guards, packaging and automated tests. Passing CI
does not establish correct in-game fit or replace local Blender render review.

## Ground rules for everything

1. **No game assets.** Never commit game files, extracted frames, sprite sheets,
   renders of game characters, models or `.blend` scenes derived from a game.
   The only images in the repository are our own procedural sample art, the
   editor's test fixture, and screenshots of those.
   `tests/integration/test_repository.py` checks for asset file types, images
   under `games/`, and machine-specific paths.
2. **No machine-specific paths.** Use paths relative to the repository, or
   settings (`launchers/_shared/config.bat`, `SPRITEMOTION_*` environment
   variables, command-line options).
3. **`common/` knows nothing about any game.** Game-specific logic belongs in
   `games/<game>/`, loaded through `game.json`.
4. Run `launchers\dev\run-tests.bat` (or `python -m pytest tests`) and, if you
   changed the editor, `launchers\dev\editor-tests.bat` before opening a pull request.

## Code

- Python 3.10+, standard library + numpy + Pillow in `common/`. Blender
  scripts must also run in Blender's bundled Python, which lacks Pillow, so
  import Pillow lazily inside functions.
- Blender scripts take their arguments after `--`, must work under
  `blender -b --factory-startup`, and must guard `main()` with
  `if __name__ == "__main__":`.
- New data files get a schema in `schemas/`, or an entry in
  [docs/annotation-format.md](docs/annotation-format.md) if they are an internal format.
- Add a test with each behaviour change. The sample character exists so that
  pipeline behaviour can be checked against known 3D ground truth.

## Annotations

Annotations are the main shared asset. The workflow:

1. Extract the frames from your own copy of the game (for UO:
   `launchers\pipeline\1-extract-uo.bat`).
2. Correct poses in the Sprite Pose Editor. Tick **Pose approved** only after
   checking every joint of that pose. Use notes for occluded or ambiguous limbs.
3. Promote your reviewed corrections into the bundle:

   ```bat
   .venvs\spritemotion\Scripts\python -m spritemotion promote workspace\ultima-online\body-400 ^
       --bundle games\ultima-online\annotations\body-400 --sequences action-000
   ```

4. Run `python -m spritemotion validate` and the tests, then open a pull
   request that says which sequences and directions you reviewed.

Reviewers check:

- every pose carries a `source_fingerprint` that matches the extracted frame
- rig projections still say `independent: false`
- approved poses were not changed without a note
- estimates were not edited in place, since corrections go in the correction layer

`promote` replaces the bundle's correction file for each promoted sequence,
so start from the bundled corrections (they are applied when you extract) and
keep the approved poses you did not mean to change. The diff shows every
approved pose that changed, and those changes need a reviewer's agreement. If you disagree with an approved pose, open an issue with a
screenshot of your *own* extraction. It stays in the issue and never goes
into the repository.

## Research notes

Findings about a game's projection, conventions or animation quirks go in
`games/<game>/research/`. State what was measured, how, and how confident you
are. Label candidates as candidates. Numbers such as silhouette IoU need their
method next to them.
