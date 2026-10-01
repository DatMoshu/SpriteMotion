# workspace/

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
