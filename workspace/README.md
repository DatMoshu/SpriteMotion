# workspace/

Task 553 moved the existing local payloads into the shared work area's `workspace/`
directory. This checkout keeps local symbolic links for legacy paths used by the
editor, pipeline launchers and authoring scripts. The data is stored outside the
checkout; preserve the links when using those legacy paths. No authoring data was
deleted. New jobs should use `SPRITEMOTION_WORK_ROOT` directly.

Generated payloads now belong under `SPRITEMOTION_WORK_ROOT` (Windows default:
`D:/_agentShared/work/spritemotion`); review screenshots, logs and clips belong in
central evidence runs. New content-studio jobs and checkout-specific Python
environments use shared work automatically. Run `python tools/worktree-venv/run.py --path`
to find this checkout's environment. Existing authoring inputs and manually edited
scenes below are retained; the conventional layout below documents legacy data.
Historical top-level review PNGs were centralized by CLEANUP-01; their original
paths and new filenames are recorded in that evidence run's move receipts.

Your local working area. **Everything here except this README is
gitignored** and must never be committed or shared. That covers extracted game
frames, your models and `.blend` files, fits, renders and comparison sheets.

Conventional layout (the launchers use it):

```text
workspace/
  ultima-online/body-400/     extracted dataset (frames, dataset.json, annotations with your corrections)
  ultima-online/model.blend   your rigged model (SPRITEMOTION_BLEND)
  fits/                       rig.json, <sequence>.json pose solutions, keyed .blend files, apply reports
  renders/                    <sequence>/d<dir>_f<frame>.png, compare JSON, contact sheets
  sample/                     output of launchers\dev\sample-loop.bat
  screenshots/                editor captures
```

To share your annotation work, promote your corrections into the repository
bundle (see [CONTRIBUTING.md](../CONTRIBUTING.md)). Never share this folder.
